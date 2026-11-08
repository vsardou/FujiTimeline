# FujiTimeline

Prova de conceito Python por linha de comando: sincroniza JPEGs Fujifilm e vídeos
de iPhone pelos metadados e gera uma timeline editável FCPXML, referenciando as
mídias originais. Sem calibração experimental, interface gráfica ou Google Drive.

O código está em **[`sincronizador-fotos-videos/`](sincronizador-fotos-videos/)**.
A estrutura local foi preservada: a raiz Git é a pasta acima do pacote Python.

- [Instalação, uso e testes no Windows/macOS](sincronizador-fotos-videos/README.md)
- [Estado do checkpoint e pendências](sincronizador-fotos-videos/docs/checkpoint.md)
- [Pesquisa e decisão do exportador](sincronizador-fotos-videos/docs/exporter-decision.md)

## Início rápido

Windows (PowerShell), a partir da raiz deste repositório:

```powershell
cd sincronizador-fotos-videos
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m fujitimeline demo --output output\demo.fcpxml --report output\demo.json
```

macOS, com Python 3.11+ instalado:

```bash
cd sincronizador-fotos-videos
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/python -m fujitimeline demo --output output/demo.fcpxml --report output/demo.json
```

O demo usa dados simulados e não exige mídias, FFprobe ou ExifTool. Para arquivos
reais, siga o README do pacote para instalar essas duas ferramentas e informar
os caminhos das mídias. Os arquivos gerados ficam em `output/`, ignorada pelo Git.

## Estado atual

CLI e testes implementados, com leitores de metadados, faixas independentes,
dois modos de duração e exportador baseado em OpenTimelineIO. O checkpoint
inicial tem 32 testes aprovados no Windows. A importação no Final Cut Pro, a
execução nativa no macOS e a sincronização das mídias reais ainda não foram
validadas. Consulte o documento de estado para o alcance exato da verificação.

O repositório é privado. A criação/push pelo Git não concede automaticamente
acesso à conexão GitHub de outra conversa: o proprietário precisa permitir
este repositório nas configurações da conexão, caso ele não apareça disponível.
