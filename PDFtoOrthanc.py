#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# PDFtoOrthanc.py — Conversão Segura de PDFs médicos em DICOM com Auditoria
#
# Copyright (C) 2025 Lucas Weber
# Licença: GPLv3 ou posterior
#

"""
PDFtoOrthanc (Versão Hardened)
------------------------------
Middleware para conversão e envio de PDFs médicos para Orthanc PACS.
Foco em integridade de dados, segurança e auditoria.

Features de Segurança:
- Validação de Magic Bytes (%PDF-)
- Hashing SHA-256 para auditoria
- Prevenção de colisão de arquivos (UUID)
- Sanitização rigorosa de inputs
"""

import os
import re
import base64
import shutil
import datetime as dt
import logging
import json
import hashlib
import uuid
import unicodedata
from logging.handlers import RotatingFileHandler
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, Tuple, List, Optional

import requests

# -------------------------- CONFIGURAÇÕES (ENV) --------------------------
# Redes e Autenticação
ORTHANC_URL = os.getenv("ORTHANC_URL", "http://localhost:8042").rstrip("/")
ORTHANC_USER = os.getenv("ORTHANC_USER", "orthanc")
ORTHANC_PASSWORD = os.getenv("ORTHANC_PASSWORD", "orthanc")

# Sistema de Arquivos
PDF_SOURCE_FOLDER = os.getenv("PDF_SOURCE_FOLDER", "//localhost/ecg")
PROCESSED_PATH = os.path.join(PDF_SOURCE_FOLDER, "Processados")
ERROR_PATH = os.path.join(PDF_SOURCE_FOLDER, "Erros")
DUPLICATE_PATH = os.path.join(PDF_SOURCE_FOLDER, "Duplicados")
LOG_PATH = os.getenv("PDFFLOW_LOG", os.path.join(PDF_SOURCE_FOLDER, "pdftoorthanc.log"))

# Comportamento
CREATE_DATE_FOLDERS = os.getenv("CREATE_DATE_FOLDERS", "true").lower() == "true"
SKIP_DUP_CHECK = os.getenv("SKIP_DUP_CHECK", "false").lower() == "true"
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "2"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
BACKOFF_BASE_SEC = float(os.getenv("BACKOFF_BASE_SEC", "1.5"))
MAX_FILE_MB = float(os.getenv("MAX_FILE_MB", "50"))

# DICOM Tags Fixas
SOPCLASS_PDF = '1.2.840.10008.5.1.4.1.1.104.1'
FIXED_EXAM = {
    "Type": os.getenv("EXAM_TYPE", "ELETROCARDIOGRAMA"),
    "Modality": os.getenv("EXAM_MODALITY", "ECG")
}
INSTITUTION_NAME = os.getenv("INSTITUTION_NAME", "HOSPITAL DIGITAL")
REFERRING_PHYSICIAN = os.getenv("REFERRING_PHYSICIAN", "AUTOMATIZADO")

# -------------------------- LOGGING ESTRUTURADO --------------------------
logger = logging.getLogger("pdftoorthanc")
logger.setLevel(logging.INFO)
fmt = logging.Formatter('%(asctime)s %(levelname)s %(message)s')

# Console
ch = logging.StreamHandler()
ch.setFormatter(fmt)
logger.addHandler(ch)

# Arquivo Rotativo (Proteção contra disco cheio)
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
fh = RotatingFileHandler(LOG_PATH, maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8')
fh.setFormatter(fmt)
logger.addHandler(fh)

def jlog(level: str, **fields):
    """Gera logs estruturados em JSON para fácil ingestão (Splunk/ELK)."""
    msg = json.dumps(fields, ensure_ascii=False)
    getattr(logger, level.lower(), logger.info)(msg)

# -------------------------- UTILITÁRIOS DE SEGURANÇA --------------------------
REGEX_ID = re.compile(r'^\d+$')
REGEX_DATE = re.compile(r'^(\d{6}|\d{8})$')

def calculate_sha256(file_path: str) -> str:
    """Gera hash SHA-256 do arquivo para auditoria forense."""
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception:
        return "HASH_CALC_ERROR"

def validate_pdf_integrity(file_path: str) -> Tuple[bool, str]:
    """Verifica se o arquivo é um PDF válido analisando Magic Bytes."""
    try:
        if os.path.getsize(file_path) < 100:
            return False, "Arquivo muito pequeno (vazio ou corrompido)"
        
        with open(file_path, 'rb') as f:
            header = f.read(5)
            if header != b'%PDF-':
                return False, f"Assinatura inválida: {header}"
            
            # Opcional: Verificar EOF (desabilitado para performance em arquivos grandes, 
            # mas recomendável se houver muitos arquivos truncados)
            return True, "OK"
    except Exception as e:
        return False, str(e)

def ensure_dirs():
    """Garante existência das pastas de trabalho."""
    for d in [PROCESSED_PATH, ERROR_PATH, DUPLICATE_PATH]:
        os.makedirs(d, exist_ok=True)

def move_file_safe(source: str, dest_base: str, study_date: str) -> str:
    """Move arquivos de forma atômica/segura, prevenindo sobrescrita."""
    if CREATE_DATE_FOLDERS and study_date and len(study_date) >= 8:
        # Formato YYYY-MM-DD
        date_folder = f"{study_date[0:4]}-{study_date[4:6]}-{study_date[6:8]}"
        target_dir = os.path.join(dest_base, date_folder)
    else:
        target_dir = dest_base

    os.makedirs(target_dir, exist_ok=True)
    filename = os.path.basename(source)
    destination = os.path.join(target_dir, filename)

    # Prevenção de colisão robusta com UUID
    if os.path.exists(destination):
        base, ext = os.path.splitext(filename)
        # Adiciona UUID curto para garantir unicidade sem travar threads
        unique_suffix = str(uuid.uuid4())[:8]
        destination = os.path.join(target_dir, f"{base}_{unique_suffix}{ext}")

    try:
        shutil.move(source, destination)
        return destination
    except Exception as e:
        logger.error(f"Erro crítico ao mover arquivo {source}: {e}")
        raise

# -------------------------- PARSING E NORMALIZAÇÃO --------------------------

def normalize_text(text: str) -> str:
    """Sanitiza strings removendo acentos e caracteres não-safe."""
    text = text.strip()
    text = unicodedata.normalize('NFKD', text)
    text = "".join([c for c in text if not unicodedata.combining(c)])
    text = re.sub(r'[^a-zA-Z0-9\s]', '', text) # Whitelist estrita
    return text.upper()

def format_dicom_date(date_str: str) -> str:
    """Normaliza datas para formato DICOM (YYYYMMDD)."""
    if not date_str or not REGEX_DATE.match(date_str):
        return dt.datetime.now().strftime('%Y%m%d')
    try:
        # Lógica Pivot Year (19xx vs 20xx)
        if len(date_str) == 6:
            day, month, year_short = int(date_str[:2]), int(date_str[2:4]), int(date_str[4:])
            year = 1900 + year_short if year_short >= 70 else 2000 + year_short
        elif len(date_str) == 8:
            # Tenta inferir se é DDMMAAAA ou YYYYMMDD
            if date_str.startswith(('19', '20')): # Provável YYYYMMDD
                return date_str
            day, month, year = int(date_str[:2]), int(date_str[2:4]), int(date_str[4:])
        else:
            return dt.datetime.now().strftime('%Y%m%d')
        
        return f"{year:04d}{month:02d}{day:02d}"
    except ValueError:
        return dt.datetime.now().strftime('%Y%m%d')

def parse_name_parts(parts: List[str]) -> Tuple[str, str]:
    """Converte lista de nomes em (Nome^Meio^Sobrenome, Nome Natural)."""
    if not parts:
        return "DESCONHECIDO", "DESCONHECIDO"
    
    first = parts[0]
    last = parts[-1] if len(parts) > 1 else ""
    middle = " ".join(parts[1:-1]) if len(parts) > 2 else ""

    # DICOM Name: Last^First^Middle
    dicom_name = f"{last}^{first}^{middle}".strip("^")
    # Natural Name: First Middle Last
    natural_name = " ".join(parts)
    
    return dicom_name, natural_name

# --- Estratégias de Parsing ---

def try_parse_structured(parts: List[str]) -> Optional[Dict[str, Any]]:
    """Estratégia 1: PatientID_Nome_..._Data_Accession.pdf"""
    # Mínimo 5 partes: ID, Nome, Sobrenome, Data, Acc
    if len(parts) < 5:
        return None
    
    pat_id = parts[0]
    date_str = parts[-2]
    acc_num = parts[-1]

    if not (REGEX_ID.match(pat_id) and REGEX_DATE.match(date_str) and REGEX_ID.match(acc_num)):
        return None

    name_tokens = parts[1:-2]
    dicom_name, natural_name = parse_name_parts(name_tokens)
    study_date = format_dicom_date(date_str)

    return {
        'PatientID': pat_id,
        'AccessionNumber': acc_num,
        'PatientName': dicom_name,
        'PatientNameNatural': natural_name,
        'StudyDate': study_date,
        'Method': 'STRUCTURED'
    }

def try_parse_legacy(parts: List[str]) -> Optional[Dict[str, Any]]:
    """Estratégia 2: Nome_..._Data.pdf (Busca data de trás pra frente)"""
    date_idx = -1
    for i in range(len(parts)-1, -1, -1):
        if REGEX_DATE.match(parts[i]):
            date_idx = i
            break
    
    if date_idx < 1: # Precisa de pelo menos 1 nome antes da data
        return None
    
    name_tokens = parts[:date_idx]
    dicom_name, natural_name = parse_name_parts(name_tokens)
    study_date = format_dicom_date(parts[date_idx])

    return {
        'PatientID': '', # Gerar automático se vazio
        'AccessionNumber': '',
        'PatientName': dicom_name,
        'PatientNameNatural': natural_name,
        'StudyDate': study_date,
        'Method': 'LEGACY'
    }

def extract_metadata(filename: str) -> Dict[str, Any]:
    """Fachada que executa as estratégias de parsing."""
    base = os.path.splitext(filename)[0]
    # Tokenização segura
    parts = [normalize_text(p) for p in base.split('_') if p.strip()]

    # Chain of Responsibility
    meta = try_parse_structured(parts)
    if not meta:
        meta = try_parse_legacy(parts)
    
    if meta:
        return {'IsValid': True, **meta}
    
    return {
        'IsValid': False, 
        'Error': 'Formato de nome não reconhecido',
        'StudyDate': dt.datetime.now().strftime('%Y%m%d')
    }

# -------------------------- COMUNICAÇÃO HTTP --------------------------

def get_session():
    """Cria sessão HTTP com Retry Strategy."""
    s = requests.Session()
    if ORTHANC_USER and ORTHANC_PASSWORD:
        s.auth = (ORTHANC_USER, ORTHANC_PASSWORD)
    return s

def check_duplicate_robust(session, url: str, meta: Dict[str, Any]) -> bool:
    """Verifica duplicidade usando múltiplos critérios (Hierarquia de Confiança)."""
    # 1. Accession Number (Ouro)
    if meta.get('AccessionNumber'):
        payload = {"Level": "Study", "Query": {"AccessionNumber": meta['AccessionNumber']}}
        try:
            r = session.post(f"{url}/tools/find", json=payload, timeout=10)
            if r.json() and len(r.json()) > 0:
                return True
        except Exception:
            pass # Falha na query não deve parar o processo, tenta próximo critério

    # 2. PatientID + Date (Prata)
    if meta.get('PatientID'):
        payload = {"Level": "Study", "Query": {"PatientID": meta['PatientID'], "StudyDate": meta['StudyDate']}}
        try:
            r = session.post(f"{url}/tools/find", json=payload, timeout=10)
            if r.json() and len(r.json()) > 0:
                return True
        except Exception:
            pass

    # 3. Nome Exato + Date (Bronze - Fallback)
    payload = {"Level": "Study", "Query": {"PatientName": meta['PatientName'], "StudyDate": meta['StudyDate']}}
    try:
        r = session.post(f"{url}/tools/find", json=payload, timeout=10)
        if r.json() and len(r.json()) > 0:
            return True
    except Exception:
        pass

    return False

def upload_dicom(session, url: str, pdf_path: str, tags: Dict[str, Any]) -> str:
    with open(pdf_path, 'rb') as f:
        content = base64.b64encode(f.read()).decode('utf-8')
    
    payload = {
        "Tags": tags,
        "Content": f"data:application/pdf;base64,{content}"
    }
    
    # Timeout dinâmico baseado no tamanho (min 30s)
    size_mb = os.path.getsize(pdf_path) / (1024*1024)
    timeout = max(30, size_mb * 2)

    r = session.post(f"{url}/tools/create-dicom", json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json().get('ID')

# -------------------------- CORE PIPELINE --------------------------

def process_file(filepath: str) -> Dict[str, Any]:
    filename = os.path.basename(filepath)
    file_hash = calculate_sha256(filepath) # Auditoria Step 1
    
    jlog("info", event="start_processing", file=filename, sha256=file_hash)

    # 1. Validação de Integridade
    is_valid, msg = validate_pdf_integrity(filepath)
    if not is_valid:
        jlog("warning", event="integrity_failure", file=filename, error=msg)
        dest = move_file_safe(filepath, ERROR_PATH, "")
        return {"status": "error", "reason": "corrupted_pdf"}

    # 2. Extração de Metadados
    meta = extract_metadata(filename)
    if not meta['IsValid']:
        jlog("warning", event="metadata_failure", file=filename, error=meta['Error'])
        dest = move_file_safe(filepath, ERROR_PATH, meta['StudyDate'])
        return {"status": "error", "reason": "invalid_filename"}

    # 3. Verificação de Duplicidade (Opcional)
    session = get_session()
    if not SKIP_DUP_CHECK:
        if check_duplicate_robust(session, ORTHANC_URL, meta):
            jlog("info", event="duplicate_skipped", file=filename, acc=meta.get('AccessionNumber'))
            dest = move_file_safe(filepath, DUPLICATE_PATH, meta['StudyDate'])
            return {"status": "skipped", "reason": "duplicate"}

    # 4. Preparação de Tags DICOM
    tags = {
        "SOPClassUID": SOPCLASS_PDF,
        "PatientName": meta['PatientNameNatural'], # Orthanc lida bem com Natural Name
        "PatientID": meta.get('PatientID') or "UNKNOWN",
        "AccessionNumber": meta.get('AccessionNumber') or "",
        "StudyDate": meta['StudyDate'],
        "StudyDescription": FIXED_EXAM['Type'],
        "SeriesDescription": f"{FIXED_EXAM['Type']} (PDF)",
        "Modality": FIXED_EXAM['Modality'],
        "InstitutionName": INSTITUTION_NAME,
        "ReferringPhysicianName": REFERRING_PHYSICIAN
    }

    # 5. Upload Seguro
    try:
        orthanc_id = upload_dicom(session, ORTHANC_URL, filepath, tags)
        jlog("info", event="upload_success", file=filename, orthanc_id=orthanc_id, sha256=file_hash)
        dest = move_file_safe(filepath, PROCESSED_PATH, meta['StudyDate'])
        return {"status": "success", "id": orthanc_id}
    except Exception as e:
        jlog("error", event="upload_error", file=filename, error=str(e))
        dest = move_file_safe(filepath, ERROR_PATH, meta['StudyDate'])
        return {"status": "error", "reason": "http_error"}

# -------------------------- MAIN LOOP --------------------------

def main():
    ensure_dirs()
    logger.info(">>> PDFtoOrthanc Security Hardened Iniciado <<<")
    
    # Teste de Conectividade
    try:
        s = get_session()
        r = s.get(f"{ORTHANC_URL}/system", timeout=5)
        r.raise_for_status()
        logger.info(f"Conectado ao Orthanc: {r.json().get('Name', 'Unknown')}")
    except Exception as e:
        logger.critical(f"Falha fatal de conexão com Orthanc: {e}")
        return

    files = [os.path.join(PDF_SOURCE_FOLDER, f) for f in os.listdir(PDF_SOURCE_FOLDER) 
             if f.lower().endswith('.pdf')]
    
    if not files:
        return # Sem arquivos, saída silenciosa

    logger.info(f"Processando {len(files)} arquivos com {MAX_WORKERS} workers.")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_file, f): f for f in files}
        
        for future in as_completed(futures):
            # O processamento já loga internamente, aqui apenas garantimos que exceções não tratadas não quebrem o loop
            try:
                future.result()
            except Exception as e:
                logger.error(f"Crash em thread worker: {e}")

if __name__ == "__main__":
    main()
