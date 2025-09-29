#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# PDFtoOrthanc.py — Conversão automática de PDFs médicos em DICOM com envio ao Orthanc PACS
#
# Copyright (C) 2025  Lucas Weber
#
# Este programa é software livre: você pode redistribuí-lo e/ou modificá-lo
# sob os termos da Licença Pública Geral GNU conforme publicada pela Free
# Software Foundation, na versão 3 da licença ou (a seu critério) qualquer
# versão posterior.
#
# Este programa é distribuído na expectativa de que seja útil,
# mas SEM QUALQUER GARANTIA; sem mesmo a garantia implícita de
# COMERCIABILIDADE ou ADEQUAÇÃO A UM DETERMINADO FIM.
# Consulte a Licença Pública Geral GNU para mais detalhes.
#
# Você deve ter recebido uma cópia da Licença Pública Geral GNU
# junto com este programa. Se não, consulte <https://www.gnu.org/licenses/>.
#

"""
PDFtoOrthanc
------------
Ferramenta para converter arquivos PDF em objetos DICOM Encapsulated PDF
e enviá-los automaticamente para um servidor Orthanc através da REST API.

Autor: Lucas Weber
Repositório: https://github.com/byweber/PDFtoOrthanc
Licença: GPLv3 ou posterior
"""

import os
import re
import base64
import shutil
import datetime as dt
import logging
from logging.handlers import RotatingFileHandler
import json
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, Tuple, List

import requests

# -------------------------- CONFIGURAÇÕES (via ENV) --------------------------
ORTHANC_URL = os.getenv("ORTHANC_URL", "http://localhost:8042").rstrip("/")
ORTHANC_USER = os.getenv("ORTHANC_USER", "orthanc")
ORTHANC_PASSWORD = os.getenv("ORTHANC_PASSWORD", "orthanc")
PDF_SOURCE_FOLDER = os.getenv("PDF_SOURCE_FOLDER", "//localhost/ecg")

PROCESSED_PATH = os.path.join(PDF_SOURCE_FOLDER, "Processados")
ERROR_PATH = os.path.join(PDF_SOURCE_FOLDER, "Erros")
DUPLICATE_PATH = os.path.join(PDF_SOURCE_FOLDER, "Duplicados")
LOG_PATH = os.getenv("PDFFLOW_LOG", os.path.join(PDF_SOURCE_FOLDER, "pdftoorthanc.log"))

CREATE_DATE_FOLDERS = os.getenv("CREATE_DATE_FOLDERS", "true").lower() == "true"
SKIP_DUP_CHECK = os.getenv("SKIP_DUP_CHECK", "false").lower() == "true"
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "2"))  # ajustar conforme capacidade do servidor
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
BACKOFF_BASE_SEC = float(os.getenv("BACKOFF_BASE_SEC", "1.5"))
MAX_FILE_MB = float(os.getenv("MAX_FILE_MB", "50"))  # preventiva, ajuste conforme Orthanc

SOPCLASS_PDF = '1.2.840.10008.5.1.4.1.1.104.1'

FIXED_EXAM = {
    "Type": os.getenv("EXAM_TYPE", "ELETROCARDIOGRAMA"),
    "Modality": os.getenv("EXAM_MODALITY", "ECG")
}

INSTITUTION_NAME = os.getenv("INSTITUTION_NAME", "HOSPITAL DIGITAL")
REFERRING_PHYSICIAN = os.getenv("REFERRING_PHYSICIAN", "AUTOMATIZADO")

# -------------------------- LOGGING --------------------------
logger = logging.getLogger("pdftoorthanc")
logger.setLevel(logging.INFO)

fmt = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
# Console
ch = logging.StreamHandler()
ch.setFormatter(fmt)
logger.addHandler(ch)
# Arquivo rotativo
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
fh = RotatingFileHandler(LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=5, encoding='utf-8')
fh.setFormatter(fmt)
logger.addHandler(fh)


def jlog(level: str, **fields):
    """Log JSON-like (campo 'msg' opcional)."""
    msg = json.dumps(fields, ensure_ascii=False)
    logger.log(getattr(logging, level.upper(), logging.INFO), msg)


# -------------------------- UTIL --------------------------
REGEX_ID = re.compile(r'^\d+$')  # Somente dígitos
REGEX_DATE = re.compile(r'^(\d{6}|\d{8})$')  # 6 ou 8 dígitos


def ensure_dirs():
    for d in [PROCESSED_PATH, ERROR_PATH, DUPLICATE_PATH]:
        os.makedirs(d, exist_ok=True)


def build_date_folder_path(base: str, study_date: str) -> str:
    if CREATE_DATE_FOLDERS and study_date and len(study_date) >= 8:
        date_folder = f"{study_date[0:4]}-{study_date[4:6]}-{study_date[6:8]}"
        return os.path.join(base, date_folder)
    return base


def normalize_name_token(token: str) -> str:
    # Normaliza Unicode, remove marcas combinantes (acentos), mantém letras e espaços
    token = token.strip()
    token = unicodedata.normalize('NFKD', token)
    token = ''.join(ch for ch in token if not unicodedata.combining(ch))
    token = re.sub(r"[^A-Za-z\s]", " ", token)  # remove números e pontuação
    token = re.sub(r"\s+", " ", token).strip()
    return token.upper()


def is_valid_name_part(token: str) -> bool:
    # Alterado para {1,} para aceitar conectivos ("e") e iniciais ("J")
    return bool(token) and re.fullmatch(r"[A-Z ]{1,}", token) is not None


def format_dicom_date(date_str: str) -> str:
    """Retorna YYYYMMDD. Suporta DDMMYY, DDMMYYYY, YYYYMMDD. Pivot YY >=70 => 19xx, senão 20xx."""
    if not date_str or not REGEX_DATE.match(date_str):
        return dt.datetime.now().strftime('%Y%m%d')
    try:
        if len(date_str) == 6:
            dd, mm, yy = int(date_str[0:2]), int(date_str[2:4]), int(date_str[4:6])
            year = 1900 + yy if yy >= 70 else 2000 + yy
            d = dt.date(year, mm, dd)
        elif len(date_str) == 8:
            if date_str[:4] in ("19" + date_str[6:8], "20" + date_str[6:8]):
                # já pode estar em YYYYMMDD
                year, mm, dd = int(date_str[0:4]), int(date_str[4:6]), int(date_str[6:8])
                d = dt.date(year, mm, dd)
            else:
                # assumir DDMMYYYY
                dd, mm, year = int(date_str[0:2]), int(date_str[2:4]), int(date_str[4:8])
                d = dt.date(year, mm, dd)
        else:
            d = dt.date.today()
        return d.strftime('%Y%m%d')
    except Exception:
        return dt.datetime.now().strftime('%Y%m%d')


def move_file_safe(source: str, dest_folder: str, study_date: str) -> str:
    final_folder = build_date_folder_path(dest_folder, study_date)
    os.makedirs(final_folder, exist_ok=True)
    filename = os.path.basename(source)
    dest = os.path.join(final_folder, filename)
    if os.path.exists(dest):
        ts = dt.datetime.now().strftime('%H%M%S')
        base, ext = os.path.splitext(filename)
        dest = os.path.join(final_folder, f"{base}-{ts}{ext}")
    shutil.move(source, dest)
    jlog("info", event="file_moved", src=source, dest=dest)
    return dest


# -------------------------- PARSING DE ARQUIVOS --------------------------

def _parse_dicom_name_parts(name_parts: List[str]) -> Tuple[str, str, str]:
    """
    Extrai o primeiro, meio e último nome de uma lista de partes do nome.
    Lógica: LastName^FirstName^MiddleName.
    Ex: ['JOAO', 'SILVA', 'DE', 'SOUZA'] -> ('JOAO', 'SILVA DE', 'SOUZA')
    """
    first_name = 'PACIENTE'
    middle_name = ''
    last_name = 'NOME'

    if not name_parts:
        return first_name, middle_name, last_name

    if len(name_parts) == 1:
        # Se houver apenas uma parte, assume-se que é o sobrenome.
        last_name = name_parts[0]
    else:  # 2 ou mais partes
        last_name = name_parts[-1]  # O último item é o Sobrenome (LastName)
        first_name = name_parts[0]  # O primeiro item é o Nome (FirstName)
        if len(name_parts) > 2:
            # O que estiver entre o primeiro e o último é o Nome do Meio (MiddleName)
            middle_name = ' '.join(name_parts[1:-1])

    return first_name, middle_name, last_name


def validate_parts(parts):
    # Para o formato ESTRUTURADO, o mínimo de partes agora é 5 (ID_Nome_Sobrenome_Data_Acc)
    if len(parts) < 5:
        return 'Formato incompleto'
    patient_id = parts[0]
    date_str = parts[-2]
    acc_num = parts[-1]
    if not REGEX_ID.match(patient_id):
        return 'PatientID deve ser somente números'
    if not REGEX_DATE.match(date_str):
        return 'Data inválida'
    if not REGEX_ID.match(acc_num):
        return 'AccessionNumber deve ser somente números'
    # Valida nome (tokens entre PatientID e Data)
    for p in parts[1:-2]:
        p_norm = normalize_name_token(p)
        if not is_valid_name_part(p_norm):
            return f"Nome inválido no campo: {p}"
    return None


def parse_filename(filename: str) -> Dict[str, Any]:
    base = os.path.splitext(filename)[0]
    parts_raw = base.split('_')
    parts = [p.strip() for p in parts_raw if p.strip()]
    err = validate_parts(parts)
    if not err:
        patient_id = parts[0]
        date_str = parts[-2]
        accession_number = parts[-1]
        name_parts_raw = parts[1:-2]

        name_parts = [normalize_name_token(p) for p in name_parts_raw]
        first_name, middle_name, last_name = _parse_dicom_name_parts(name_parts)

        study_date = format_dicom_date(date_str)
        return {
            'IsValid': True,
            'Format': 'ESTRUTURADO',
            'PatientID': patient_id,
            'FirstName': first_name,
            'MiddleName': middle_name,
            'LastName': last_name,
            'DateString': date_str,
            'StudyDate': study_date,
            'AccessionNumber': accession_number,
            'HasIds': True,
            'Error': None
        }

    # LEGADO: procurar último token de data válido
    date_index = -1
    for i in range(len(parts) - 1, -1, -1):
        if REGEX_DATE.match(parts[i]):
            try:
                _ = format_dicom_date(parts[i])
                date_index = i
                break
            except Exception:
                continue

    if date_index > 0 and date_index >= 2:  # Precisa de pelo menos Nome_Sobrenome_Data
        name_parts_raw = parts[:date_index]
        name_parts = [normalize_name_token(p) for p in name_parts_raw]
        first_name, middle_name, last_name = _parse_dicom_name_parts(name_parts)

        study_date = format_dicom_date(parts[date_index])
        return {
            'IsValid': True,
            'Format': 'LEGADO',
            'PatientID': '',
            'FirstName': first_name,
            'MiddleName': middle_name,
            'LastName': last_name,
            'DateString': parts[date_index],
            'StudyDate': study_date,
            'AccessionNumber': '',
            'HasIds': False,
            'Error': None
        }

    return {
        'IsValid': False,
        'Format': 'INVALIDO',
        'PatientID': '',
        'FirstName': 'ERRO',
        'MiddleName': '',
        'LastName': 'FORMATO',
        'DateString': '',
        'StudyDate': dt.datetime.now().strftime('%Y%m%d'),
        'AccessionNumber': '',
        'HasIds': False,
        'Error': 'Formato inválido'
    }


# -------------------------- ORTHANC --------------------------

def get_auth_header(user: str, password: str) -> Dict[str, str]:
    headers = {}
    if user and password:
        auth = f"{user}:{password}"
        b64auth = base64.b64encode(auth.encode()).decode()
        headers['Authorization'] = f"Basic {b64auth}"
    return headers


def req_with_retry(method: str, url: str, session: requests.Session, headers: Dict[str, str],
                   json_body: Dict[str, Any] | None = None, timeout: float = 60.0) -> requests.Response:
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = session.request(method=method, url=url, headers=headers, json=json_body, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception as e:
            last_exc = e
            wait = BACKOFF_BASE_SEC ** attempt
            jlog("warning", event="http_retry", attempt=attempt, wait_s=round(wait, 2), url=url, error=str(e))
            try:
                import time
                time.sleep(wait)
            except Exception:
                pass
    raise last_exc  # esgota as tentativas


def test_orthanc_connection(url: str, headers: Dict[str, str]) -> Tuple[bool, str]:
    with requests.Session() as s:
        try:
            r = req_with_retry("GET", f"{url}/system", s, headers, timeout=10)
            version = r.json().get('Version', '')
            return True, version
        except Exception as e:
            return False, str(e)


# --- INÍCIO DO BLOCO ALTERADO ---
def find_duplicate(accession: str | None, patient_id: str | None,
                   patient_name_dicom: str | None, patient_name_natural: str | None,
                   study_date: str, url: str, headers: Dict[str, str]) -> Tuple[bool, str | None]:
    """
    Verifica duplicados com uma hierarquia robusta:
    1. AccessionNumber
    2. PatientID + StudyDate
    3. PatientName (formato DICOM: SOBRENOME^NOME) + StudyDate
    4. PatientName (formato Natural: NOME SOBRENOME) + StudyDate
    """
    with requests.Session() as s:
        # 1) Por AccessionNumber
        if accession:
            try:
                body = {"Level": "Study", "Query": {"AccessionNumber": accession}}
                r = req_with_retry("POST", f"{url}/tools/find", s, {**headers, 'Content-Type': 'application/json'}, body, timeout=30)
                data = r.json()
                if data:
                    jlog("info", event="duplicate_found", method="accession", value=accession, study_id=data[0])
                    return True, data[0]
            except Exception as e:
                jlog("warning", event="find_accession_failed", accession=accession, error=str(e))

        # 2) Por PatientID + StudyDate
        if patient_id:
            try:
                body = {"Level": "Study", "Query": {"PatientID": patient_id, "StudyDate": study_date}}
                r = req_with_retry("POST", f"{url}/tools/find", s, {**headers, 'Content-Type': 'application/json'}, body, timeout=30)
                data = r.json()
                if data:
                    jlog("info", event="duplicate_found", method="patient_id_date", value=patient_id, study_id=data[0])
                    return True, data[0]
            except Exception as e:
                jlog("warning", event="find_patient_date_failed", patient_id=patient_id, study_date=study_date, error=str(e))

        # 3) Por PatientName (formato DICOM) + StudyDate
        if patient_name_dicom:
            try:
                body = {"Level": "Study", "Query": {"PatientName": patient_name_dicom, "StudyDate": study_date}}
                r = req_with_retry("POST", f"{url}/tools/find", s, {**headers, 'Content-Type': 'application/json'}, body, timeout=30)
                data = r.json()
                if data:
                    jlog("info", event="duplicate_found", method="patient_name_dicom", value=patient_name_dicom, study_id=data[0])
                    return True, data[0]
            except Exception as e:
                jlog("warning", event="find_patient_name_dicom_failed", name=patient_name_dicom, study_date=study_date, error=str(e))

        # 4) Por PatientName (formato Natural) + StudyDate - Fallback final
        if patient_name_natural and patient_name_natural.replace(" ", "") != patient_name_dicom.replace("^", ""):
            try:
                body = {"Level": "Study", "Query": {"PatientName": patient_name_natural, "StudyDate": study_date}}
                r = req_with_retry("POST", f"{url}/tools/find", s, {**headers, 'Content-Type': 'application/json'}, body, timeout=30)
                data = r.json()
                if data:
                    jlog("info", event="duplicate_found", method="patient_name_natural", value=patient_name_natural, study_id=data[0])
                    return True, data[0]
            except Exception as e:
                jlog("warning", event="find_patient_name_natural_failed", name=patient_name_natural, study_date=study_date, error=str(e))

    return False, None
# --- FIM DO BLOCO ALTERADO ---


def send_pdf_as_dicom(pdf_path: str, url: str, headers: Dict[str, str], tags: Dict[str, Any]) -> Dict[str, Any]:
    size_mb = round(os.path.getsize(pdf_path) / (1024 * 1024), 2)
    if size_mb > MAX_FILE_MB:
        raise RuntimeError(f"PDF acima do limite permitido: {size_mb} MB > {MAX_FILE_MB} MB")
    with open(pdf_path, 'rb') as f:
        pdf_bytes = f.read()
    pdf_b64 = base64.b64encode(pdf_bytes).decode()
    payload = {"Tags": tags, "Content": f"data:application/pdf;base64,{pdf_b64}"}
    timeout = max(60.0, 15.0 + size_mb * 1.5)  # timeout proporcional ao tamanho
    with requests.Session() as s:
        r = req_with_retry("POST", f"{url}/tools/create-dicom", s, {**headers, 'Content-Type': 'application/json'},
                           payload, timeout=timeout)
        return r.json()


# -------------------------- PROCESSAMENTO --------------------------

def process_file(full_path: str, orthanc_url: str, headers: Dict[str, str]) -> Dict[str, Any]:
    name = os.path.basename(full_path)
    jlog("info", event="processing_start", file=name)
    parsed = parse_filename(name)
    if not parsed['IsValid']:
        jlog("warning", event="invalid_format", file=name, reason=parsed['Error'])
        moved = move_file_safe(full_path, ERROR_PATH, '')
        return {'Success': False, 'Skipped': True, 'Reason': 'Formato de arquivo inválido', 'File': name,
                'MovedTo': moved}

    # Monta os dois formatos de nome para busca e para a tag
    pn_parts_for_search = [parsed.get('LastName', ''), parsed.get('FirstName', ''), parsed.get('MiddleName', '')]
    while pn_parts_for_search and not pn_parts_for_search[-1]:
        pn_parts_for_search.pop()
    patient_name_for_search = '^'.join(pn_parts_for_search)

    name_parts_for_tag = [parsed.get('FirstName', ''), parsed.get('MiddleName', ''), parsed.get('LastName', '')]
    patient_name_for_tag = ' '.join(part for part in name_parts_for_tag if part)

    if not SKIP_DUP_CHECK:
        # --- INÍCIO DO BLOCO ALTERADO ---
        # A chamada da função agora passa os DOIS formatos de nome
        exists, study_id = find_duplicate(
            accession=parsed.get('AccessionNumber') or None,
            patient_id=parsed.get('PatientID') or None,
            patient_name_dicom=patient_name_for_search,
            patient_name_natural=patient_name_for_tag,
            study_date=parsed['StudyDate'],
            url=orthanc_url,
            headers=headers
        )
        # --- FIM DO BLOCO ALTERADO ---
        if exists:
            jlog("info", event="duplicate_detected", file=name, accession=parsed.get('AccessionNumber'),
                 study_id=study_id)
            moved = move_file_safe(full_path, DUPLICATE_PATH, parsed['StudyDate'])
            return {'Success': False, 'Skipped': True, 'Duplicate': True,
                    'AccessionNumber': parsed.get('AccessionNumber', ''), 'File': name, 'Reason': 'Estudo já existe',
                    'MovedTo': moved}

    hhmmss = dt.datetime.now().strftime('%H%M%S')
    tags = {
        "PatientName": patient_name_for_tag,
        "StudyDescription": FIXED_EXAM['Type'],
        "StudyDate": parsed['StudyDate'],
        "StudyTime": hhmmss,
        "SeriesDescription": f"{FIXED_EXAM['Type']} - PDF",
        "SeriesDate": parsed['StudyDate'],
        "SeriesTime": hhmmss,
        "SeriesNumber": "1",
        "Modality": FIXED_EXAM['Modality'],
        "ContentDate": parsed['StudyDate'],
        "ContentTime": hhmmss,
        "InstanceNumber": "1",
        "InstitutionName": INSTITUTION_NAME,
        "ReferringPhysicianName": REFERRING_PHYSICIAN,
        "SOPClassUID": SOPCLASS_PDF
    }
    if parsed['PatientID']:
        tags['PatientID'] = parsed['PatientID']
    if parsed['AccessionNumber']:
        tags['AccessionNumber'] = parsed['AccessionNumber']

    try:
        resp = send_pdf_as_dicom(full_path, orthanc_url, headers, tags)
        size_mb = round(os.path.getsize(full_path) / (1024 * 1024), 2)
        jlog("info", event="sent_success", file=name, size_mb=size_mb, instance_id=resp.get('ID'))
        moved = move_file_safe(full_path, PROCESSED_PATH, parsed['StudyDate'])
        return {'Success': True, 'InstanceId': resp.get('ID'), 'FileSize': size_mb, 'File': name, 'MovedTo': moved}
    except Exception as e:
        jlog("error", event="send_failed", file=name, error=str(e))
        moved = move_file_safe(full_path, ERROR_PATH, '')
        return {'Success': False, 'Error': str(e), 'File': name, 'MovedTo': moved}


# -------------------------- MAIN --------------------------

def main():
    logger.info("=== PDF para Orthanc v2 (Python) ===")

    folder = PDF_SOURCE_FOLDER
    if not os.path.isdir(folder):
        logger.error(f"Pasta inválida ou não encontrada: {folder}. Saindo.")
        return

    ensure_dirs()

    headers = get_auth_header(ORTHANC_USER, ORTHANC_PASSWORD)
    connected, info = test_orthanc_connection(ORTHANC_URL, headers)
    if not connected:
        logger.error(f"Falha na conexão com Orthanc: {info}")
        return
    logger.info(f"Conectado ao Orthanc, versão: {info}")

    files = [f for f in os.listdir(folder) if f.lower().endswith('.pdf')]
    if len(files) == 0:
        logger.warning("Nenhum arquivo PDF encontrado na pasta.")
        return

    logger.info(f"Arquivos encontrados: {len(files)} | workers={MAX_WORKERS}")

    total_ok = 0
    total_dup = 0
    total_err = 0

    file_paths = [os.path.join(folder, f) for f in files]

    if MAX_WORKERS > 1:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = {ex.submit(process_file, p, ORTHANC_URL, headers): p for p in file_paths}
            for fut in as_completed(futures):
                res = fut.result()
                if res.get('Success'):
                    total_ok += 1
                elif res.get('Duplicate'):
                    total_dup += 1
                else:
                    total_err += 1
    else:
        for p in file_paths:
            res = process_file(p, ORTHANC_URL, headers)
            if res.get('Success'):
                total_ok += 1
            elif res.get('Duplicate'):
                total_dup += 1
            else:
                total_err += 1

    summary = {"processados": total_ok, "Duplicados": total_dup, "erros": total_err}
    jlog("info", event="summary", **summary)
    print("Resumo do processamento:")
    print(f"  Processados com sucesso: {total_ok}")
    print(f"  Duplicados puladas: {total_dup}")
    print(f"  Erros: {total_err}")


if __name__ == "__main__":
    main()
