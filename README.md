# PDFtoOrthanc

Ferramenta em **Python** para automatizar o envio de arquivos **PDF** (como exames de ECG) para o servidor **Orthanc**, convertendo-os em objetos **DICOM** e organizando os arquivos localmente.

## ✨ Funcionalidades

* Leitura de arquivos PDF em uma pasta de origem (ex.: compartilhamento SMB/CIFS montado).
* Parsing e validação de nomes de arquivos (extraindo `PatientID`, nome, data e `AccessionNumber`).
* Criação automática de **tags DICOM** para envio ao Orthanc.
* Checagem de duplicidade no Orthanc por:

  * `AccessionNumber`
  * `PatientID + StudyDate` (fallback)
* Envio dos PDFs como objetos DICOM via **API REST do Orthanc**.
* Organização dos arquivos em subpastas:

  * `Processados`
  * `Duplicatas`
  * `Erros`
  * (opcionalmente organizados também por data)
* Logs estruturados em console e arquivo rotativo.
* Retentativas com **backoff exponencial** em falhas de rede.
* Processamento paralelo configurável (`ThreadPoolExecutor`).

---

## 📦 Dependências

* Python **3.x**
* [requests](https://pypi.org/project/requests/)

  ```bash
  pip install requests
  ```
* [cifs-utils](https://wiki.samba.org/index.php/LinuxCIFS_utils) (opcional, caso use SMB/CIFS no Linux)

  ```bash
  sudo apt install cifs-utils
  ```

---

## ⚙️ Configuração

Todos os parâmetros podem ser definidos por variáveis de ambiente (valores padrão inclusos):

| Variável              | Padrão                        | Descrição                                     |
| --------------------- | ----------------------------- | --------------------------------------------- |
| `ORTHANC_URL`         | `http://localhost:8042`       | URL do Orthanc                                |
| `ORTHANC_USER`        | `USER`                        | Usuário do Orthanc                            |
| `ORTHANC_PASSWORD`    | `PASSWORD`                    | Senha do Orthanc                              |
| `PDF_SOURCE_FOLDER`   | `/mnt/ecg`                    | Pasta de origem dos PDFs                      |
| `CREATE_DATE_FOLDERS` | `true`                        | Cria subpastas por data                       |
| `SKIP_DUP_CHECK`      | `false`                       | Ignora checagem de duplicidade                |
| `MAX_WORKERS`         | `2`                           | Número de threads para processamento paralelo |
| `MAX_RETRIES`         | `3`                           | Tentativas em falha de rede                   |
| `BACKOFF_BASE_SEC`    | `1.5`                         | Fator de backoff exponencial                  |
| `MAX_FILE_MB`         | `50`                          | Tamanho máximo permitido por PDF              |
| `INSTITUTION_NAME`    | `HOSPITAL DIGITAL`            | Nome da instituição                           |
| `REFERRING_PHYSICIAN` | `AUTOMATIZADO`                | Médico responsável                            |

---

## ▶️ Uso manual

```bash
ORTHANC_URL=http://localhost:8042 \\
ORTHANC_USER=alice ORTHANC_PASSWORD=alice \\
PDF_SOURCE_FOLDER=/mnt/ecg \\
python3 PDFtoOrthanc_v2.py
```

---

## ⏰ Automação com Crontab

Para rodar a cada **30 minutos** e registrar logs:

```bash
*/30 * * * * ORTHANC_URL=http://localhost:8042 ORTHANC_USER=USER ORTHANC_PASSWORD=PASSWORD PDF_SOURCE_FOLDER=/mnt/ecg /usr/bin/python3 /caminho/para/PDFtoOrthanc.py >> /caminho/para/log_pdftoorthanc.log 2>&1
```

---

## 📂 Organização de pastas

Após o processamento, os arquivos serão movidos automaticamente para:

* `Processados/YYYY-MM-DD/`
* `Duplicatas/YYYY-MM-DD/`
* `Erros/YYYY-MM-DD/`

Com geração automática de subpastas por data (opcional).

---

## 📜 Licença

Este projeto é distribuído sob a licença **MIT**.

---
