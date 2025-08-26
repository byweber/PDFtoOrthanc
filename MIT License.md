# MIT License

**PDFtoOrthanc.py - Sistema de Automação para Conversão PDF para DICOM/Orthanc PACS**

Copyright (c) 2024 Lucas Weber

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

---

## Sobre o Projeto

**PDFtoOrthanc.py** é uma ferramenta Python desenvolvida por **Lucas Weber** para automatizar o processo de conversão e envio de arquivos PDF (principalmente exames de ECG) para sistemas Orthanc PACS (Picture Archiving and Communication System).

**Repositório Oficial:** https://github.com/byweber/PDFtoOrthanc

### Funcionalidades Principais

- Automação completa do processamento batch de arquivos PDF
- Conversão para objetos DICOM padronizados
- Validação robusta de dados e nomenclatura de arquivos
- Detecção inteligente de duplicatas
- Processamento paralelo para otimização de performance
- Sistema avançado de retry com backoff exponencial
- Logging estruturado em formato JSON
- Organização automática de arquivos por categoria

### Desenvolvido para

Este software foi especialmente desenvolvido para hospitais e clínicas que necessitam integrar documentos PDF digitalizados em ambientes PACS, oferecendo uma solução robusta, escalável e confiável para modernização de fluxos de trabalho médicos.

### Autor Principal

**Lucas Weber**  
GitHub: https://github.com/byweber

### Agradecimentos e Créditos

Este projeto não seria possível sem o trabalho excepcional e o suporte da comunidade:

#### **Equipe Orthanc**
Agradecimentos especiais à **equipe de desenvolvimento do Orthanc** pelo desenvolvimento e manutenção do Orthanc, PACS de código aberto, que serve como base fundamental para esta solução de automação:

- **Sébastien Jodogne** - Criador e mantenedor principal do Orthanc
- **Alain Mazy** - Desenvolvedor core e contribuidor principal
- Toda a **equipe de desenvolvedores Orthanc** que contribuem continuamente para a evolução da plataforma

**Orthanc Project:** https://www.orthanc-server.com/

#### **Comunidade Orthanc Users**
Reconhecimento especial aos membros da **comunidade Orthanc Users** que forneceram suporte, orientações técnicas e soluções para desafios específicos durante o desenvolvimento:

- **Orthanc Discourse Forum** - Fórum oficial da comunidade
- **Orthanc Book** - Documentação técnica abrangente
- **Contribuidores do Stack Overflow** que responderam questões relacionadas ao Orthanc
- **Desenvolvedores da comunidade** que compartilharam scripts e soluções similares
- **Usuários beta** que testaram versões preliminares e forneceram feedback valioso

**Comunidade:** https://discourse.orthanc-server.org/  
**Documentação:** https://book.orthanc-server.com/

#### **Tecnologias Utilizadas**
- **Python 3.7+** - Linguagem de programação principal
- **Requests Library** - Para comunicação HTTP com Orthanc
- **Orthanc REST API** - Interface de comunicação com o PACS
- **DICOM Standard** - Padrão de imagens médicas

### Bases Técnicas

Este projeto foi desenvolvido com base em:
- **Documentação oficial do Orthanc** e suas APIs REST
- **Padrões DICOM** para estruturação de objetos médicos
- **Melhores práticas** compartilhadas pela comunidade Orthanc Users
- **Exemplos de código** disponíveis na documentação e fóruns
- **Experiências práticas** de implementações similares na comunidade

### Instalação e Uso

Para instruções detalhadas de instalação, configuração e uso, consulte o repositório oficial:

**Repositório:** https://github.com/byweber/PDFtoOrthanc

### Contribuições

Contribuições são bem-vindas! Se você deseja contribuir para este projeto:

1. Faça um fork do repositório: https://github.com/byweber/PDFtoOrthanc
2. Crie uma branch para sua feature (`git checkout -b feature/nova-feature`)
3. Commit suas mudanças (`git commit -am 'Adiciona nova feature'`)
4. Push para a branch (`git push origin feature/nova-feature`)
5. Abra um Pull Request no repositório oficial

### Suporte e Comunidade

Para questões técnicas relacionadas ao PDFtoOrthanc:
- **Issues GitHub:** https://github.com/byweber/PDFtoOrthanc/issues
- **Documentação:** README no repositório oficial
- **Contato direto:** Entre em contato através do GitHub

Para questões relacionadas ao Orthanc:
- Consulte a **documentação oficial**: https://book.orthanc-server.com/
- Participe do **fórum da comunidade**: https://discourse.orthanc-server.org/

### Histórico de Versões

- **v1.0.0** (2025) - Versão inicial com funcionalidades completas de automação
  - Processamento batch automatizado
  - Validação de arquivos estruturados e legados
  - Integração completa com Orthanc PACS via REST API
  - Sistema de monitoramento e logs avançados
  - Baseado nas melhores práticas da comunidade Orthanc

**Changelog completo:** https://github.com/byweber/PDFtoOrthanc/releases

### Relatório de Bugs e Melhorias

Para relatar bugs, solicitar funcionalidades ou sugerir melhorias:

- **GitHub Issues:** https://github.com/byweber/PDFtoOrthanc/issues
- **Discussões:** https://github.com/byweber/PDFtoOrthanc/discussions

### Disclaimer e Conformidade

**Sobre o Orthanc:** Este projeto utiliza e integra com o Orthanc, um servidor PACS de código aberto. O Orthanc é desenvolvido independentemente e possui sua própria licença. Consulte a documentação oficial do Orthanc para informações sobre licenciamento e conformidade.

**Uso em Ambientes Médicos:** Este software foi desenvolvido para uso em ambientes hospitalares e clínicos. Certifique-se de seguir todas as regulamentações locais de proteção de dados médicos (como LGPD, HIPAA, etc.) ao implementar esta solução.

**Limitação de Responsabilidade:** O autor não se responsabiliza pelo uso inadequado do software ou por danos resultantes de sua implementação incorreta. É responsabilidade do usuário garantir que a solução seja implementada de acordo com as melhores práticas de segurança e conformidade regulatória.

---

**Reconhecimento Final:** Este projeto representa um esforço colaborativo baseado no trabalho excepcional da equipe Orthanc e no conhecimento compartilhado pela comunidade global de usuários. Agradecemos a todos que contribuíram direta ou indiretamente para tornar esta solução possível.

**Links Úteis:**
- **PDFtoOrthanc Repository:** https://github.com/byweber/PDFtoOrthanc
- **Orthanc Official Website:** https://www.orthanc-server.com/
- **Orthanc Documentation:** https://book.orthanc-server.com/
- **Orthanc Community Forum:** https://discourse.orthanc-server.org/
- **DICOM Standard:** https://www.dicomstandard.org/

**Se este projeto foi útil para você, considere dar uma estrela no GitHub!**
