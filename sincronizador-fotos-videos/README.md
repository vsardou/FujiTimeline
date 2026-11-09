# FujiTimeline — prova de conceito CLI

Projeto pessoal em Python 3.11+ para sincronizar JPEGs Fujifilm com vídeos de iPhone
pelos metadados de captura e gerar uma timeline editável FCPXML 1.8. Desenvolvido
inicialmente no Windows; código e caminhos portáveis para macOS. Importação no
Final Cut Pro ainda exige validação em um Mac.

Não renderiza, copia, altera nem recomprime mídias. Escreve apenas novos arquivos
JSON/FCPXML e perfis locais. Sem perfil selecionado, o offset é zero. A atualização
autorizada permite calibração opcional, incluindo o preset experimental de
−2,272 s, sempre por seleção explícita. A pasta `sincronizador-fotos-videos` foi mantida; o pacote
e o comando se chamam `fujitimeline`.

## Instalação no Windows (PowerShell)

Dentro da pasta deste README:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m fujitimeline demo --output output\demo.fcpxml --report output\demo.json
```

A ativação do ambiente é opcional; esses comandos não exigem mudar a política de
execução do PowerShell. O demo e os testes não exigem FFprobe, ExifTool ou mídias.

Para arquivos reais, instale [FFmpeg/FFprobe](https://ffmpeg.org/download.html)
e [ExifTool](https://exiftool.org/install.html). Na distribuição Windows do
ExifTool, siga as instruções do pacote, mantendo suas dependências junto ao
executável. Coloque ambos no PATH ou passe `--ffprobe` e `--exiftool` com caminhos
completos. Verifique `ffprobe -version` e `exiftool -ver` em um novo terminal.

## Instalação no macOS

Com Python 3.11+ instalado; para quem usa Homebrew:

```bash
brew install python ffmpeg exiftool
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest
.venv/bin/python -m fujitimeline demo --output output/demo.fcpxml --report output/demo.json
```

Dependências Python: OpenTimelineIO 0.18.1, adaptador otio-fcpx-xml-adapter 1.0.0,
tzdata; pytest para desenvolvimento. As duas primeiras estão fixadas porque o
exportador estende pontos internos do adaptador. Não há dependência de GUI ou Drive.

## Uso real

Primeiro inspecione o plano sem exportar XML:

```powershell
.\.venv\Scripts\python.exe -m fujitimeline plan --video "C:\Midias\IMG_2050.MOV" --photos "C:\Midias\JPEG" --output output\plano.json
```

Se alguma data não tiver fuso, o programa para com uma mensagem. Informe o fuso
real da câmera, por exemplo `--assume-timezone America/Sao_Paulo` ou
`--assume-timezone=-03:00`. Isso interpreta uma data incompleta; não calibra relógios.
Um offset existente no arquivo sempre tem prioridade. Não presume o fuso do Windows.

Exemplo com dois vídeos e efeito opcional:

```powershell
.\.venv\Scripts\python.exe -m fujitimeline export --video "C:\Midias\a.mov" "C:\Midias\b.mov" --photos "C:\Midias\JPEG" --assume-timezone America/Sao_Paulo --mode fixed --fixed-duration 3 --tolerance 2 --shutter "C:\Midias\disparo.wav" --fps 30 --output output\FujiTimeline.fcpxml --report output\FujiTimeline.json
```

No macOS use `.venv/bin/python` e caminhos como `/Volumes/Midias/a.mov`. `--video`
aceita uma lista; `--recursive` inclui subpastas de JPEGs. Use ponto nos decimais.
`--width 1920 --height 1080` define o formato de projeto; por padrão são usadas
as dimensões codificadas do primeiro vídeo. Para vídeo com metadados de rotação,
confira a orientação no Final Cut e informe as dimensões de projeto desejadas.

### Calibração opcional

O sinal é **horário corrigido da foto = horário original + offset**.
−2,272 s antecipa a foto em relação ao relógio do vídeo. A correção precede
seleção e posicionamento; o EXIF original nunca é alterado. Não são inferidos
modelos de aparelhos. Identifique o seu par com um rótulo local como `meu-par`.

```powershell
.\.venv\Scripts\python.exe -m fujitimeline demo --profile experimental-minus-2.272 --pair-id meu-par --report output\demo-experimental.json
.\.venv\Scripts\python.exe -m fujitimeline profile create --preset experimental-minus-2.272 --pair-id meu-par --output profiles\meu-par-v1.profile.json
```

Para reutilizar em `plan`/`export`, adicione
`--profile profiles\meu-par-v1.profile.json --pair-id meu-par` ao comando.
Omitir `--profile` mantém zero, mesmo que existam perfis salvos. Um perfil de outro
par é recusado. O relatório inclui perfil, revisão, status, offset e horários
originais/corrigidos de todas as fotos lidas, inclusive as excluídas.

`profile validate` verifica correspondências fornecidas pelo usuário;
`profile recalibrate` estima um novo offset e salva uma nova revisão. Ambos
avaliam início/fim da sessão e possível deriva antes de marcar `validated`.
Veja [o formato das evidências e os comandos completos](docs/calibration.md).
O preset permanece **experimental**; não há correspondências reais verificadas
nesta entrega. Os testes de validação usam dados simulados.

`--mode until_next` é o padrão. `--fps` aceita 24, 25, 30, 50, 60,
24000/1001, 30000/1001 ou 60000/1001. Arquivos de saída existentes são recusados;
use um nome novo para cada execução. `python -m fujitimeline --help` lista os comandos.

## Semântica temporal

- Vídeo: FFprobe em JSON; prioridade para `com.apple.quicktime.creationdate`,
  depois `creation_time`, no contêiner e na faixa de vídeo. Considera a data
  selecionada como início da gravação. Duração: `duration_ts × time_base`,
  depois duração da faixa/contêiner. Não utiliza datas de criação/modificação do disco.
- JPEG: ExifTool, `SubSecDateTimeOriginal`, ou composição de `DateTimeOriginal`,
  `SubSecTimeOriginal` e `OffsetTimeOriginal`. Falta de horário é erro explícito.
- Frações de segundo arbitrárias são mantidas como `Fraction`; UTC serve para
  comparar instantes. Valor original, tag de origem, offset e fuso informado
  pelo usuário são preservados no JSON. Um offset selecionado é somado a esse
  instante UTC antes da filtragem, preservando o valor original. Horários IANA ambíguos/inexistentes por
  horário de verão são recusados: forneça um offset explícito.
- Vídeos são ordenados pelo início e concatenados integralmente no plano exato.
  Intervalos sem gravação são removidos. Fotos dentro de `[início, fim)` têm
  prioridade; em gravações sobrepostas cada foto entra uma vez, no primeiro
  vídeo cronológico que a contém, com aviso.
- Tolerância padrão 0, faixa permitida 0–60 s inclusive. Fora de uma gravação,
  escolhe a borda mais próxima dentro da tolerância. Limita a foto ao início
  ou ao último quadro visível desse vídeo; registra o deslocamento original e
  um aviso. Isso é uma regra de borda, não correção do relógio.
- `until_next`: até a próxima foto na timeline compacta; a última vai até o fim.
  Pode atravessar um corte entre vídeos. `fixed`: menor valor entre duração fixa,
  próxima foto e fim da timeline.
- WAV opcional: repetido no início de cada foto, em lane de áudio independente;
  corta o som na próxima foto ou no fim, se necessário. O áudio original do vídeo
  continua referenciado. Fotos no mesmo instante são erro, nunca descartadas em silêncio.
- Exportação: somente a cópia para edição usa a grade de quadros. Inícios de fotos
  são arredondados ao quadro mais próximo; a cauda de cada vídeo inferior a um
  quadro é omitida da edição para não extrapolar a mídia. O plano exato permanece
  intacto. O relatório informa as posições exportadas e essas diferenças.
  Colisões de fotos no mesmo quadro são recusadas; aumente FPS ou selecione menos fotos.

## Estrutura

```text
src/fujitimeline/
  selection.py       seleção de arquivos com pathlib
  metadata.py        leitores FFprobe/ExifTool, somente leitura
  models.py          dataclasses de mídias e posicionamentos
  temporal.py        parsing de datas, fusos e frações
  calibration.py     perfis opcionais, revisões, evidências e deriva
  timeline.py        filtragem e timeline compacta exata
  otio_builder.py    faixas OTIO e ajuste de quadros para exportação
  export_fcpxml.py   adaptador FCPXML e correções isoladas
  report.py         relatório JSON e gravação sem sobrescrita
  cli.py            comandos plan, export e demo
  demo.py           cenário simulado solicitado
tests/              metadados, cálculo, CLI e XML
docs/exporter-decision.md  pesquisa e justificativa
```

## Cenário de aceitação simulado

Vídeo de **24,398 s**; quatro fotos nos tempos solicitados, sem calibração:

| Foto | Início exato (s) | until_next (s) | fixed=3 (s) |
|---|---:|---:|---:|
| 1 | 12,660 | 4,220 | 3,000 |
| 2 | 16,880 | 2,950 | 2,950 |
| 3 | 19,830 | 3,590 | 3,000 |
| 4 | 23,420 | 0,978 | 0,978 |

O FCPXML do `demo` referencia caminhos fictícios em `example-media`; ele serve
para testar a estrutura, não para afirmar importação de mídias reais.

## Próxima validação com arquivos reais

1. Instalar/verificar FFprobe e ExifTool. Rodar `plan` com o MOV e os quatro JPEGs
   originais. Confirmar as tags selecionadas, fusos e frações no relatório;
   não forçar os tempos do demo sobre as mídias reais.
2. Rodar `export`, com um WAV se desejado. Conferir no relatório seleção de fotos,
   diferenças de grade de quadros e eventuais avisos de tolerância.
3. No Mac, preferir gerar o XML a partir dos caminhos reais desse Mac. Um URI
   `file:///C:/...` do Windows não existe no macOS: use o recurso de relink do
   Final Cut ou gere novamente apontando às mídias em um volume acessível.
   O FujiTimeline não transporta os arquivos.
4. Validar com a DTD oficial **FCPXML 1.8** (não uma DTD de outra versão):
   `xmllint --noout --dtdvalid /caminho/FCPXMLv1_8.dtd output/FujiTimeline.fcpxml`.
   Obtenha a DTD no [suporte do Final Cut](https://support.apple.com/final-cut-pro).
5. No Final Cut Pro, importar XML e conferir quatro fotos editáveis acima dos
   vídeos, disparos independentes no mesmo quadro, áudio original, ausência de
   vazios entre gravações, duração, orientação, cor/HDR e resolução. Registrar
   a versão do Final Cut, erros de importação e um XML exportado por ele para comparação.

**Limites desta entrega:** testes automatizados e demo local não comprovam a
importação no Final Cut. Não há mapeamento automático Windows→Mac, correção automática de
deriva entre relógios (ela é estimada e pode impedir a validação), transições, tratamento especial de HDR/rotação, nem
validação visual de vídeos VFR ou taxas mistas. O formato dos assets usa o FPS
do projeto; VFR/HEVC/HDR e conformação pelo Final Cut precisam da prova real.
Metadados podem descrever criação do contêiner em vez da captura, ou vir de um
relógio impreciso; o programa os utiliza literalmente por padrão, ou soma apenas
o offset explicitamente selecionado. A validação matemática depende de
correspondências reais conferidas pelo usuário e só cobre a sessão medida.
