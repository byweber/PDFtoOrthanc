#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDFtoOrthanc.py

*************************************************************
                HOSPITAL MUNICIPAL SAO JOSE
             AREA DE TECNOLOGIA DA INFORMACAO
 ------------------------------------------------------------- 
 Criacao.......: Lucas de Souza Weber
 Data/Criacao..: 08 de Agosto de 2025
 Data/versao...: 07 de Setembro de 2025
 Revisao.......: 4
 *************************************************************

Descrição geral:
Esta ferramenta automatiza o envio de arquivos PDF (exames de ECG ou outros documentos clínicos digitalizados) para o Orthanc, convertendo-os em objetos DICOM e organizando os arquivos em pastas locais.

Principais funcionalidades:
- Leitura de arquivos PDF em uma pasta de origem.
- Validação de conteúdo para identificar e isolar PDFs corrompidos.
- Parsing do nome dos arquivos via Expressão Regular configurável ou por um padrão fixo, extraindo PatientID, Nome, Data e AccessionNumber.
- Criação de tags DICOM adequadas para envio ao Orthanc.
- Checagem de duplicidade no Orthanc.
- Envio dos PDFs como DICOM via API REST do Orthanc.
- Movimentação segura dos arquivos para subpastas (Processados, Erros, Duplicatas).
- Logs estruturados (console e arquivo rotativo) em formato JSON.
- Retentativas automáticas em falhas de rede/Orthanc com backoff exponencial.
- Processamento paralelo configurável para melhor desempenho.

Dependências:
- Python 3.x
- requests (pip install requests)
- PyPDF2 (pip install PyPDF2)
- cifs-utils (caso seja necessário montar compartilhamento SMB/CIFS no Linux)

Configuração via variáveis de ambiente (com valores padrão):
- ORTHANC_URL (default: http://localhost:8042)
- ORTHANC_USER (default: alice)
- ORTHANC_PASSWORD (default: alice)
- PDF_SOURCE_FOLDER (default: /mnt/ecg)
- FILENAME_REGEX_PATTERN (Opcional, ex: '^(?P<patient_id>\d+)_(?P<name_parts>.*)_(?P<date>\d{6,8})_(?P<accession>\d+)$')
- CREATE_DATE_FOLDERS (default: true)
- SKIP_DUP_CHECK (default: false)
- MAX_WORKERS (default: 2)
- MAX_RETRIES (default: 3)
- BACKOFF_BASE_SEC (default: 1.5)
- MAX_FILE_MB (default: 50)
- INSTITUTION_NAME (default: HOSPITAL DIGITAL)
- REFERRING_PHYSICIAN (default: AUTOMATIZADO)

Exemplo de uso manual:
ORTHANC_URL=http://localhost:8042 \\
PDF_SOURCE_FOLDER=/mnt/ecg \\
python3 PDFtoOrthanc_v4.py

Exemplo com Regex customizado:
FILENAME_REGEX_PATTERN='^(?P<patient_id>\d+)_(?P<name_parts>.*)_(?P<date>\d{8})_(?P<accession>\d+)$' \\
python3 PDFtoOrthanc_v4.py

---
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
from typing import Dict, Any, Tuple

import requests
try:
    import PyPDF2
    from PyPDF2.errors import PdfReadError
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False


# -------------------------- CONFIGURAÇÕES (via ENV) --------------------------
ORTHANC_URL = os.getenv("ORTHANC_URL", "http://localhost:8042").rstrip("/")
ORTHANC_USER = os.getenv("ORTHANC_USER", "alice")
ORTHANC_PASSWORD = os.getenv("ORTHANC_PASSWORD", "alice")
PDF_SOURCE_FOLDER = os.getenv("PDF_SOURCE_FOLDER", "/mnt/ecg")

# NOVO: Permite um Regex customizado para o nome do arquivo
FILENAME_REGEX_PATTERN = os.getenv("FILENAME_REGEX_PATTERN", None)

PROCESSED_PATH = os.path.join(PDF_SOURCE_FOLDER, "Processados")
ERROR_PATH = os.path.join(PDF_SOURCE_FOLDER, "Erros")
DUPLICATE_PATH = os.path.join(PDF_SOURCE_FOLDER, "Duplicatas")
LOG_PATH = os.getenv("PDFFLOW_LOG", os.path.join(PDF_SOURCE_FOLDER, "pdftoorthanc.log"))

CREATE_DATE_FOLDERS = os.getenv("CREATE_DATE_FOLDERS", "true").lower() == "true"
SKIP_DUP_CHECK = os.getenv("SKIP_DUP_CHECK", "false").lower() == "true"
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "2"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
BACKOFF_BASE_SEC = float(os.getenv("BACKOFF_BASE_SEC", "1.5"))
MAX_FILE_MB = float(os.getenv("MAX_FILE_MB", "50"))

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
ch = logging.StreamHandler()
ch.setFormatter(fmt)
logger.addHandler(ch)
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
fh = RotatingFileHandler(LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=5, encoding='utf-8')
fh.setFormatter(fmt)
logger.addHandler(fh)


def jlog(level: str, **fields):
    """Log JSON-like."""
    msg = json.dumps(fields, ensure_ascii=False)
    logger.log(getattr(logging, level.upper(), logging.INFO), msg)


# -------------------------- UTIL --------------------------
REGEX_ID = re.compile(r'^\d+$')
REGEX_DATE = re.compile(r'^(\d{6}|\d{8})$')


def ensure_dirs():
    for d in [PROCESSED_PATH, ERROR_PATH, DUPLICATE_PATH]:
        os.makedirs(d, exist_ok=True)


def build_date_folder_path(base: str, study_date: str) -> str:
    if CREATE_DATE_FOLDERS and study_date and len(study_date) >= 8:
        date_folder = f"{study_date[0:4]}-{study_date[4:6]}-{study_date[6:8]}"
        return os.path.join(base, date_folder)
    return base


def normalize_name_token(token: str) -> str:
    token = token.strip()
    token = unicodedata.normalize('NFKD', token)
    token = ''.join(ch for ch in token if not unicodedata.combining(ch))
    token = re.sub(r"[^A-Za-z\s]", " ", token)
    token = re.sub(r"\s+", " ", token).strip()
    return token.upper()


def is_valid_name_part(token: str) -> bool:
    return bool(token) and re.fullmatch(r"[A-Z ]{2,}", token) is not None


def format_dicom_date(date_str: str) -> str:
    if not date_str or not REGEX_DATE.match(date_str):
        return dt.datetime.now().strftime('%Y%m%d')
    try:
        if len(date_str) == 6:
            dd, mm, yy = int(date_str[0:2]), int(date_str[2:4]), int(date_str[4:6])
            year = 1900 + yy if yy >= 70 else 2000 + yy
            d = dt.date(year, mm, dd)
        elif len(date_str) == 8:
            if date_str[:4] in ("19" + date_str[6:8], "20" + date_str[6:8]):
                year, mm, dd = int(date_str[0:4]), int(date_str[4:6]), int(date_str[6:8])
                d = dt.date(year, mm, dd)
            else:
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

def validate_parts_structured(parts):
    if len(parts) < 5: return 'Formato incompleto'
    if not REGEX_ID.match(parts[0]): return 'PatientID deve ser somente números'
    if not REGEX_DATE.match(parts[-2]): return 'Data inválida'
    if not REGEX_ID.match(parts[-1]): return 'AccessionNumber deve ser somente números'
    for p in parts[1:-2]:
        if not is_valid_name_part(normalize_name_token(p)):
            return f"Nome inválido no campo: {p}"
    return None

def _parse_with_regex(base_name: str) -> Dict[str, Any] | None:
    """Tenta fazer o parsing usando o Regex customizado."""
    if not FILENAME_REGEX_PATTERN:
        return None
    
    match = re.match(FILENAME_REGEX_PATTERN, base_name)
    if not match:
        return None
    
    data = match.groupdict()
    patient_id = data.get('patient_id', '')
    accession_number = data.get('accession', '')
    date_str = data.get('date', '')
    name_parts_raw = data.get('name_parts', 'PACIENTE').split('_')
    name_parts = [normalize_name_token(p) for p in name_parts_raw]
    
    last = name_parts[0] if len(name_parts) >= 1 else 'PACIENTE'
    first = ' '.join(name_parts[1:]) if len(name_parts) > 1 else 'PACIENTE'
    study_date = format_dicom_date(date_str)
    
    return {
        'IsValid': True, 'Format': 'REGEX', 'PatientID': patient_id,
        'FirstName': first, 'LastName': last, 'DateString': date_str,
        'StudyDate': study_date, 'AccessionNumber': accession_number,
        'HasIds': bool(patient_id and accession_number), 'Error': None
    }

def _parse_fallback(base_name: str) -> Dict[str, Any]:
    """Lógica original de parsing (estruturado e legado)."""
    parts_raw = base_name.split('_')
    parts = [p.strip() for p in parts_raw if p.strip()]
    
    # Tentativa 1: Formato estruturado
    err = validate_parts_structured(parts)
    if not err:
        name_parts = [normalize_name_token(p) for p in parts[1:-2]]
        last = name_parts[0] if len(name_parts) >= 1 else 'PACIENTE'
        first = ' '.join(name_parts[1:]) if len(name_parts) > 1 else 'PACIENTE'
        return {
            'IsValid': True, 'Format': 'ESTRUTURADO', 'PatientID': parts[0],
            'FirstName': first, 'LastName': last, 'DateString': parts[-2],
            'StudyDate': format_dicom_date(parts[-2]), 'AccessionNumber': parts[-1],
            'HasIds': True, 'Error': None
        }

    # Tentativa 2: Formato legado
    date_index = -1
    for i in range(len(parts) - 1, -1, -1):
        if REGEX_DATE.match(parts[i]):
            try:
                _ = format_dicom_date(parts[i]); date_index = i; break
            except Exception: continue
    
    if date_index > 0:
        name_tokens = [normalize_name_token(p) for p in parts[:date_index]]
        first = name_tokens[0] if name_tokens else 'PACIENTE'
        last = ' '.join(name_tokens[1:]) if len(name_tokens) > 1 else 'PACIENTE'
        return {
            'IsValid': True, 'Format': 'LEGADO', 'PatientID': '', 'FirstName': first,
            'LastName': last, 'DateString': parts[date_index],
            'StudyDate': format_dicom_date(parts[date_index]), 'AccessionNumber': '',
            'HasIds': False, 'Error': None
        }

    return {
        'IsValid': False, 'Format': 'INVALIDO', 'PatientID': '', 'FirstName': 'ERRO',
        'LastName': 'FORMATO', 'DateString': '', 'StudyDate': dt.datetime.now().strftime('%Y%m%d'),
        'AccessionNumber': '', 'HasIds': False, 'Error': 'Formato de nome de arquivo inválido'
    }

def parse_filename(filename: str) -> Dict[str, Any]:
    base = os.path.splitext(filename)[0]
    parsed_data = _parse_with_regex(base)
    if parsed_data:
        return parsed_data
    return _parse_fallback(base)

# -------------------------- ORTHANC --------------------------

def get_auth_header(user: str, password: str) -> Dict[str, str]:
    if user and password:
        auth = base64.b64encode(f"{user}:{password}".encode()).decode()
        return {'Authorization': f"Basic {auth}"}
    return {}

def req_with_retry(method: str, url: str, session: requests.Session, **kwargs) -> requests.Response:
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = session.request(method=method, url=url, **kwargs)
            r.raise_for_status()
            return r
        except Exception as e:
            last_exc = e
            wait = BACKOFF_BASE_SEC ** attempt
            jlog("warning", event="http_retry", attempt=attempt, wait_s=round(wait, 2), url=url, error=str(e))
            import time; time.sleep(wait)
    raise last_exc

def test_orthanc_connection(url: str, headers: Dict[str, str]) -> Tuple[bool, str]:
    with requests.Session() as s:
        try:
            r = req_with_retry("GET", f"{url}/system", s, headers=headers, timeout=10)
            return True, r.json().get('Version', '')
        except Exception as e:
            return False, str(e)

def find_duplicate(accession: str, patient_id: str, study_date: str, url: str, headers: Dict[str, str]) -> Tuple[bool, str | None]:
    with requests.Session() as s:
        if accession:
            try:
                body = {"Level": "Study", "Query": {"AccessionNumber": accession}}
                r = req_with_retry("POST", f"{url}/tools/find", s, headers=headers, json=body, timeout=30)
                if r.json(): return True, r.json()[0].get("ID")
            except Exception as e:
                jlog("warning", event="find_accession_failed", accession=accession, error=str(e))
        if patient_id:
            try:
                body = {"Level": "Study", "Query": {"PatientID": patient_id, "StudyDate": study_date}}
                r = req_with_retry("POST", f"{url}/tools/find", s, headers=headers, json=body, timeout=30)
                if r.json(): return True, r.json()[0].get("ID")
            except Exception as e:
                jlog("warning", event="find_patient_date_failed", patient_id=patient_id, study_date=study_date, error=str(e))
    return False, None

def send_pdf_as_dicom(pdf_path: str, url: str, headers: Dict[str, str], tags: Dict[str, Any]) -> Dict[str, Any]:
    size_mb = round(os.path.getsize(pdf_path) / (1024 * 1024), 2)
    if size_mb > MAX_FILE_MB:
        raise RuntimeError(f"PDF > {MAX_FILE_MB}MB: {size_mb}MB")
    with open(pdf_path, 'rb') as f:
        pdf_b64 = base64.b64encode(f.read()).decode()
    payload = {"Tags": tags, "Content": f"data:application/pdf;base64,{pdf_b64}"}
    timeout = max(60.0, 15.0 + size_mb * 1.5)
    with requests.Session() as s:
        r = req_with_retry("POST", f"{url}/tools/create-dicom", s, headers=headers, json=payload, timeout=timeout)
        return r.json()

# -------------------------- PROCESSAMENTO --------------------------

def build_dicom_tags(parsed_data: Dict[str, Any]) -> Dict[str, str]:
    """Cria o dicionário de tags DICOM a partir dos dados parseados."""
    hhmmss = dt.datetime.now().strftime('%H%M%S')
    tags = {
        "PatientName": f"{parsed_data['LastName']}^{parsed_data['FirstName']}",
        "StudyDescription": FIXED_EXAM['Type'],
        "StudyDate": parsed_data['StudyDate'], "StudyTime": hhmmss,
        "SeriesDescription": f"{FIXED_EXAM['Type']} - PDF",
        "SeriesDate": parsed_data['StudyDate'], "SeriesTime": hhmmss,
        "SeriesNumber": "1", "Modality": FIXED_EXAM['Modality'],
        "ContentDate": parsed_data['StudyDate'], "ContentTime": hhmmss,
        "InstanceNumber": "1", "InstitutionName": INSTITUTION_NAME,
        "ReferringPhysicianName": REFERRING_PHYSICIAN, "SOPClassUID": SOPCLASS_PDF
    }
    if parsed_data.get('PatientID'): tags['PatientID'] = parsed_data['PatientID']
    if parsed_data.get('AccessionNumber'): tags['AccessionNumber'] = parsed_data['AccessionNumber']
    return tags

def process_file(full_path: str, orthanc_url: str, headers: Dict[str, str]) -> Dict[str, Any]:
    name = os.path.basename(full_path)
    jlog("info", event="processing_start", file=name)

    # MELHORIA: Validar se o PDF não está corrompido
    if PYPDF2_AVAILABLE:
        try:
            with open(full_path, 'rb') as f:
                PyPDF2.PdfReader(f)
        except (PdfReadError, Exception) as e:
            jlog("error", event="corrupted_pdf", file=name, error=str(e))
            moved_to = move_file_safe(full_path, ERROR_PATH, '')
            return {'Success': False, 'Reason': 'PDF corrompido ou ilegível', 'MovedTo': moved_to}

    parsed = parse_filename(name)
    if not parsed['IsValid']:
        jlog("warning", event="invalid_format", file=name, reason=parsed['Error'])
        moved = move_file_safe(full_path, ERROR_PATH, '')
        return {'Success': False, 'Skipped': True, 'Reason': 'Formato de arquivo inválido', 'File': name, 'MovedTo': moved}

    if not SKIP_DUP_CHECK:
        acc = parsed.get('AccessionNumber')
        pid = parsed.get('PatientID')
        sdate = parsed['StudyDate']
        exists, study_id = find_duplicate(acc, pid, sdate, orthanc_url, headers)
        if exists:
            jlog("info", event="duplicate_detected", file=name, accession=acc, study_id=study_id)
            moved = move_file_safe(full_path, DUPLICATE_PATH, parsed['StudyDate'])
            return {'Success': False, 'Skipped': True, 'Duplicate': True, 'AccessionNumber': acc, 'File': name, 'Reason': 'Estudo já existe', 'MovedTo': moved}

    tags = build_dicom_tags(parsed)
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
    logger.info("=== PDF para Orthanc v4 (Python) ===")
    if not PYPDF2_AVAILABLE:
        logger.warning("Biblioteca PyPDF2 não encontrada. A validação de PDFs corrompidos será pulada. Instale com: pip install PyPDF2")

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
    if not files:
        logger.info("Nenhum arquivo PDF encontrado na pasta.")
        return

    logger.info(f"Arquivos encontrados: {len(files)} | workers={MAX_WORKERS}")

    summary = {"processados": 0, "duplicatas": 0, "erros": 0}
    file_paths = [os.path.join(folder, f) for f in files]

    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS) if MAX_WORKERS > 1 else None
    
    def process_and_update_summary(result):
        if result.get('Success'):
            summary['processados'] += 1
        elif result.get('Duplicate'):
            summary['duplicatas'] += 1
        else:
            summary['erros'] += 1

    if executor:
        with executor as ex:
            futures = {ex.submit(process_file, p, ORTHANC_URL, headers): p for p in file_paths}
            for fut in as_completed(futures):
                process_and_update_summary(fut.result())
    else: # Processamento sequencial
        for p in file_paths:
            res = process_file(p, ORTHANC_URL, headers)
            process_and_update_summary(res)

    jlog("info", event="summary", **summary)
    print("\nResumo do processamento:")
    print(f"  - Processados com sucesso: {summary['processados']}")
    print(f"  - Duplicatas puladas:      {summary['duplicatas']}")
    print(f"  - Erros:                   {summary['erros']}")

if __name__ == "__main__":
    main()
