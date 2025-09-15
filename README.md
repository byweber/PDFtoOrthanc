# PDFtoOrthanc

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Uma ferramenta Python para converter arquivos PDF médicos em formato DICOM e enviá-los automaticamente para um servidor Orthanc PACS.

## 📋 Características

- ✅ Conversão automática de PDFs para DICOM (SOP Class: Encapsulated PDF)
- ✅ Detecção de arquivos PDF corrompidos
- ✅ Verificação de duplicatas baseada em múltiplos critérios
- ✅ Processamento paralelo com controle de workers
- ✅ Organização automática em pastas por data
- ✅ Retry automático com backoff exponencial
- ✅ Logs estruturados em JSON
- ✅ Suporte a dois formatos de nomenclatura de arquivo
- ✅ Validação rigorosa de nomes de pacientes

## 🚀 Instalação

### Pré-requisitos

- Python 3.8 ou superior
- Servidor Orthanc configurado e acessível
- Bibliotecas Python: `requests`

### Instalação das dependências

```bash
pip install requests
```

## 📁 Estrutura de Arquivos

O script organiza automaticamente os arquivos processados:

```
PDF_SOURCE_FOLDER/
├── arquivo1.pdf          # Arquivos a processar
├── arquivo2.pdf
├── Processados/          # PDFs enviados com sucesso
│   └── 2024-01-15/      # Organizados por data (opcional)
├── Duplicados/           # PDFs que já existem no Orthanc
│   └── 2024-01-15/
├── Erros/                # PDFs com erro no processamento
└── pdftoorthanc.log     # Arquivo de log
```

## 📝 Formato dos Arquivos PDF

### Formato Estruturado (Recomendado)
```
PatientID_FirstName_MiddleName_LastName_Date_AccessionNumber.pdf
```

**Exemplo:** `12345_JOAO_SILVA_SANTOS_15012024_98765.pdf`

- **PatientID**: Apenas números
- **Nomes**: Apenas letras e espaços
- **Data**: DDMMAAAA ou DDMMAA
- **AccessionNumber**: Apenas números

### Formato Legado
```
FirstName_MiddleName_LastName_Date.pdf
```

**Exemplo:** `MARIA_OLIVEIRA_15012024.pdf`

## ⚙️ Configuração

### Variáveis de Ambiente

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `ORTHANC_URL` | `http://localhost:8042` | URL do servidor Orthanc |
| `ORTHANC_USER` | `orthanc` | Usuário do Orthanc |
| `ORTHANC_PASSWORD` | `orthanc` | Senha do Orthanc |
| `PDF_SOURCE_FOLDER` | `//localhost/ecg` | Pasta com os PDFs |
| `CREATE_DATE_FOLDERS` | `true` | Criar subpastas por data |
| `SKIP_DUP_CHECK` | `false` | Pular verificação de duplicatas |
| `MAX_WORKERS` | `2` | Número de threads paralelas |
| `MAX_RETRIES` | `3` | Tentativas de retry |
| `BACKOFF_BASE_SEC` | `1.5` | Base do backoff exponencial |
| `MAX_FILE_MB` | `50` | Tamanho máximo do arquivo (MB) |
| `EXAM_TYPE` | `ELETROCARDIOGRAMA` | Tipo do exame |
| `EXAM_MODALITY` | `ECG` | Modalidade DICOM |
| `INSTITUTION_NAME` | `HOSPITAL DIGITAL` | Nome da instituição |
| `REFERRING_PHYSICIAN` | `AUTOMATIZADO` | Médico solicitante |
| `PDFFLOW_LOG` | `{PDF_SOURCE_FOLDER}/pdftoorthanc.log` | Caminho do log |

### Exemplo de configuração com arquivo `.env`

```bash
# .env
ORTHANC_URL=http://seu-servidor-orthanc:8042
ORTHANC_USER=admin
ORTHANC_PASSWORD=senha_segura
PDF_SOURCE_FOLDER=/caminho/para/pdfs
MAX_WORKERS=4
MAX_FILE_MB=100
INSTITUTION_NAME=Hospital XYZ
```

## 🖥️ Uso

### Execução básica

```bash
python PDFtoOrthanc.py
```

### Execução com variáveis de ambiente

```bash
export ORTHANC_URL="http://192.168.1.100:8042"
export PDF_SOURCE_FOLDER="/dados/ecg"
export MAX_WORKERS=4
python PDFtoOrthanc.py
```

## 🔍 Verificação de Duplicatas

O script verifica duplicatas usando quatro métodos diferentes:

1. **AccessionNumber** (mais confiável)
2. **PatientID + StudyDate**
3. **PatientName (formato DICOM) + StudyDate**
4. **PatientName (formato natural) + StudyDate**

## 📊 Logs

Os logs são gerados em formato JSON estruturado:

```json
{
  "event": "processing_start",
  "file": "12345_JOAO_SILVA_15012024_98765.pdf"
}
{
  "event": "sent_success",
  "file": "12345_JOAO_SILVA_15012024_98765.pdf",
  "size_mb": 2.5,
  "instance_id": "abc123-def456-ghi789"
}
```

### Principais eventos de log:

- `processing_start`: Início do processamento
- `corrupted_pdf`: PDF corrompido detectado
- `duplicate_found`: Duplicata encontrada
- `sent_success`: Envio bem-sucedido
- `send_failed`: Erro no envio
- `summary`: Resumo final

## 🛡️ Validações

### Validação de PDF
- Verifica cabeçalho `%PDF-`
- Verifica marcador de fim `%%EOF`
- Tamanho mínimo de 1KB

### Validação de Nomes
- Remove acentos e caracteres especiais
- Converte para maiúsculas
- Valida formato de nomes

### Validação de Dados
- PatientID: apenas números
- Datas: formato DDMMAAAA ou DDMMAA
- AccessionNumber: apenas números

## 🔧 Troubleshooting

### Problemas Comuns

**Erro de conexão com Orthanc:**
```
Falha na conexão com Orthanc: Connection refused
```
- Verifique se o Orthanc está rodando
- Confirme URL, usuário e senha
- Teste conectividade de rede

**Arquivo movido para pasta "Erros":**
- Verifique o formato do nome do arquivo
- Confirme se o PDF não está corrompido
- Consulte os logs para detalhes

**Performance lenta:**
- Ajuste `MAX_WORKERS` baseado no hardware
- Verifique latência de rede com Orthanc
- Considere `MAX_FILE_MB` se arquivos são grandes

## 📈 Performance

### Recomendações de Hardware

- **CPU**: 2+ cores para processamento paralelo
- **RAM**: 2GB+ (baseado no tamanho dos PDFs)
- **Rede**: Latência baixa com servidor Orthanc
- **Disco**: SSD para I/O rápido

### Configurações de Performance

```bash
# Para servidor dedicado
MAX_WORKERS=8
MAX_FILE_MB=100

# Para ambiente compartilhado
MAX_WORKERS=2
MAX_FILE_MB=50
```

## 🤝 Contribuição

1. Faça fork do projeto
2. Crie uma branch para sua feature (`git checkout -b feature/nova-funcionalidade`)
3. Commit suas mudanças (`git commit -am 'Adiciona nova funcionalidade'`)
4. Push para a branch (`git push origin feature/nova-funcionalidade`)
5. Abra um Pull Request

## 📄 Licença

Este projeto está licenciado sob a Licença MIT - veja o arquivo [LICENSE](LICENSE) para detalhes.

## 🚀 Roadmap

- [ ] Interface web para monitoramento
- [ ] Suporte a outros formatos de arquivo
- [ ] Dashboard de métricas
- [ ] Notificações automáticas
- [ ] Processamento em lote com agenda

---

**Desenvolvido com ❤️ para facilitar a integração de documentos médicos com sistemas PACS**
