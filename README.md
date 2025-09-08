# PDF to Orthanc

Uma ferramenta de automação para integrar arquivos PDF, como laudos de ECG e outros documentos clínicos, a um servidor PACS Orthanc. O script monitora uma pasta, converte os PDFs em objetos DICOM com metadados extraídos do nome do arquivo e os envia de forma segura para o Orthanc.

## O Problema Resolvido

Muitos equipamentos médicos ou sistemas legados geram laudos e exames em formato PDF. Esses arquivos não são nativamente compatíveis com o padrão DICOM, o que dificulta sua centralização e visualização em um sistema PACS. Esta ferramenta serve como uma "ponte", automatizando completamente o processo de conversão e envio, garantindo a integridade e a organização dos dados no ambiente clínico.

## Principais Funcionalidades

  - **🤖 Automação Completa:** Monitora uma pasta de origem e processa novos arquivos PDF automaticamente.
  - **📄 Validação de Arquivos:** Verifica se os PDFs não estão corrompidos antes do processamento.
  - **✍️ Extração de Metadados:** Realiza o parsing inteligente dos nomes de arquivo para extrair dados essenciais como ID do Paciente, Nome, Data do Exame e Accession Number.
  - **⚙️ Altamente Configurável:** Todas as configurações são feitas via variáveis de ambiente, sem necessidade de alterar o código.
  - **🔄 Tolerante a Falhas:** Inclui um sistema de retentativas com *backoff* exponencial para lidar com instabilidades de rede ou do servidor Orthanc.
  - **🔍 Detecção de Duplicatas:** Evita o envio de exames duplicados, verificando a existência no Orthanc pelo Accession Number ou ID do Paciente + Data.
  - **🗂️ Organização Inteligente:** Move os arquivos processados para subpastas de `Processados`, `Erros` e `Duplicatas`, com opção de organização por data.
  - **⚡ Processamento Paralelo:** Capaz de processar múltiplos arquivos simultaneamente para otimizar o desempenho.
  - **📜 Logging Estruturado:** Gera logs detalhados em formato JSON, facilitando o monitoramento e a depuração.

## Pré-requisitos

  - Python 3.7+
  - `pip` (gerenciador de pacotes Python)
  - Acesso de rede ao servidor Orthanc.
  - (Opcional, para Linux) `cifs-utils` para montar compartilhamentos de rede Windows (SMB/CIFS).

## Instalação

1.  **Clone o repositório:**

    ```bash
    git clone https://github.com/byweber/PDFtoOrthanc.git
    cd PDFtoOrthanc
    ```

2.  **Instale as dependências:**
    Crie um arquivo `requirements.txt` com o conteúdo abaixo:

    ```
    requests
    PyPDF2
    ```

    Em seguida, instale as dependências:

    ```bash
    pip install -r requirements.txt
    ```

## Configuração

O script é configurado através de variáveis de ambiente. Você pode defini-las no seu terminal ou em um script de inicialização.

| Variável de Ambiente | Descrição | Padrão |
| :--- | :--- | :--- |
| `ORTHANC_URL` | URL base do seu servidor Orthanc. | `http://localhost:8042` |
| `ORTHANC_USER` | Usuário para autenticação no Orthanc. | `alice` |
| `ORTHANC_PASSWORD` | Senha para autenticação no Orthanc. | `alice` |
| `PDF_SOURCE_FOLDER` | Caminho completo para a pasta a ser monitorada. | `/mnt/ecg` |
| `FILENAME_REGEX_PATTERN` | (Avançado) Expressão Regular para parsear nomes de arquivo. | `(nenhum)` |
| `CREATE_DATE_FOLDERS`| `true` para criar subpastas por data (YYYY-MM-DD) nos diretórios de destino. | `true` |
| `SKIP_DUP_CHECK` | `true` para pular a verificação de duplicatas (não recomendado em produção). | `false` |
| `MAX_WORKERS` | Número de arquivos a processar em paralelo. | `2` |
| `MAX_RETRIES` | Número máximo de retentativas em caso de falha de conexão. | `3` |
| `INSTITUTION_NAME` | Nome da Instituição a ser inserido na tag DICOM. | `HOSPITAL DIGITAL` |
| `EXAM_TYPE` | Descrição do Estudo (StudyDescription). | `ELETROCARDIOGRAMA` |
| `EXAM_MODALITY` | Modalidade do exame. | `ECG` |

## Padrão de Nomenclatura dos Arquivos

Para que os metadados sejam extraídos corretamente, os arquivos PDF devem seguir um padrão de nome.

#### Padrão Estruturado (Recomendado)

O formato ideal é `IDpaciente_SOBRENOME_NOME_DATAexame_ACCESSION.pdf`.

  - **Exemplo:** `12345_SILVA_JOAO_MARIA_07092025_98765.pdf`

#### Padrão com Regex Customizado

Você pode definir sua própria lógica de parsing através da variável `FILENAME_REGEX_PATTERN`. A regex deve usar "grupos de captura nomeados" (`?P<nome>...`).

  - **Grupos disponíveis:** `patient_id`, `name_parts`, `date`, `accession`.
  - **Exemplo:** Para um padrão `ECG-ID-NOME-DATA.pdf`
    ```bash
    export FILENAME_REGEX_PATTERN='^ECG-(?P<patient_id>\d+)-(?P<name_parts>.*)_(?P<date>\d{8})$'
    ```

#### Padrão Legado (Fallback)

Se os padrões acima falharem, o script tentará encontrar a última ocorrência de uma data (`DDMMYY` ou `DDMMYYYY`) no nome do arquivo e usará o texto anterior como o nome do paciente.

  - **Exemplo:** `JOAO_SILVA_EXAME_070925.pdf`

## Uso

### Execução Manual

Defina as variáveis de ambiente e execute o script diretamente.

```bash
export ORTHANC_URL="http://localhost:8042"
export ORTHANC_USER="orthanc"
export ORTHANC_PASSWORD="mypassword"
export PDF_SOURCE_FOLDER="/mnt/share/ecg_pdfs"

python3 PDFtoOrthanc.py
```

### Automação com Cron

Para executar o script periodicamente (ex: a cada 30 minutos), edite o seu crontab (`crontab -e`):

```crontab
*/30 * * * * /usr/bin/python3 /caminho/completo/para/PDFtoOrthanc.py >> /var/log/pdftoorthanc.log 2>&1
```

*Lembre-se de definir as variáveis de ambiente no próprio arquivo do cron ou em um script que ele chame.*

## Estrutura de Arquivos

O script organiza os arquivos processados na pasta de origem para fácil auditoria.

```
/mnt/ecg/
├── 12345_SILVA_JOAO_07092025_98765.pdf   <-- Arquivo a ser processado
├── pdftoorthanc.log                      <-- Arquivo de log
├── Processados/
│   └── 2025-09-07/                       <-- Arquivos processados com sucesso
│       └── 12345_SILVA_JOAO_07092025_98765.pdf
├── Erros/
│   └── ARQUIVO_COM_NOME_INVALIDO.pdf     <-- Arquivos com erro de formato ou corrompidos
└── Duplicatas/
    └── 2025-09-07/
        └── OUTRO_ARQUIVO_JA_EXISTENTE.pdf  <-- Arquivos de exames já existentes no Orthanc
```

## Licença

Este projeto está licenciado sob a Licença MIT. Veja o arquivo `LICENSE` para mais detalhes.
