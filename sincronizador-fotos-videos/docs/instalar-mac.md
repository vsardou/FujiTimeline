# FujiTimeline no Mac

Esta é uma distribuição em Python, com iniciadores para Mac. Ainda não é um
aplicativo independente assinado nem um instalador DMG. Funciona com a pasta
em qualquer localização: não depende do usuário ou dos caminhos do Mac original.

1. Com acesso ao repositório privado, baixe o ZIP da branch `codex/fujitimeline`
   e extraia. Entre em `sincronizador-fotos-videos`.
2. Instale Python 3.11 ou superior pelo instalador macOS de
   https://www.python.org/downloads/macos/ (inclui Tkinter).
3. Instale FFmpeg (fornece FFprobe) e ExifTool. Se já usa Homebrew:
   `brew install ffmpeg exiftool`. Para instalar Homebrew consulte https://brew.sh/.
   Também é possível indicar os executáveis nos campos avançados do programa.
4. Abra `Instalar no Mac.command`. Isso cria `.venv` localmente e instala as
   dependências declaradas no projeto; requer internet na primeira instalação.
5. Abra `Abrir FujiTimeline.command`. Se o ZIP perdeu a permissão de execução,
   no Terminal dentro dessa pasta execute `chmod +x *.command`.

Como alternativa, no Terminal dentro da pasta:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m fujitimeline.gui
```

Selecione vídeos e pasta JPEG, confira a prévia, escolha um destino novo e gere
FCPXML + JSON. Os originais não são alterados. Imagens sem data de captura são
ignoradas com aviso; só fotos nos períodos dos vídeos entram na timeline.
Correção começa em zero: calibração de outra gravação não deve ser presumida.
Abra o FCPXML no Final Cut e confira visualmente o primeiro e o último disparo.

## Atualização de 11/11/2026

Exportador corrigido para formatos verticais sem nome de preset inventado,
FPS racional da fonte separado do FPS do projeto e timecode SMPTE de fonte
(inclusive drop-frame). Exporta FCPXML 1.14, com media-rep e videoSources.
Requer Final Cut que aceite FCPXML 1.14; versões anteriores não foram testadas.
Validação real: vídeo DJI Mimo vertical a 29,97 fps com origem 08:30:32;19,
quatro JPEGs e disparos importaram sem avisos no Final Cut em 11/11/2026.
Isso confirma estrutura e disponibilidade de mídia, não calibração visual.
Os scripts de instalação foram verificados sintaticamente; a instalação completa
em um segundo Mac ainda precisa ser testada.

Para atualizar, baixe uma nova cópia do código e repita a instalação. Não copie
a `.venv` de outro computador. Mantenha suas mídias e saídas fora da pasta do código.

## Aplicativo empacotado — Apple Silicon

Pacote de teste 0.1.1 para macOS 12+ e M1 ou mais novo:
[baixar aplicativo](https://github.com/vsardou/FujiTimeline/releases/download/v0.1.1-mac/FujiTimeline-0.1.1-macOS-AppleSilicon.zip).
Extraia e arraste FujiTimeline.app para Aplicativos. Não precisa instalar Python,
Homebrew, FFmpeg ou ExifTool. O ExifTool incluído usa /usr/bin/perl do macOS.
Final Cut/Resolve não estão incluídos. Não serve para Mac Intel.

Assinatura ad-hoc, sem notarização Apple: o macOS pode bloquear a abertura inicial.
O pacote foi aberto após extração em outra pasta no Mac de desenvolvimento, com
PATH limitado ao sistema, leitura real de mídia e exportações dos dois perfis.
Ainda falta teste em um segundo Mac. 91 testes automatizados passaram.
O código de build está em packaging/build-mac.sh; requer PyInstaller 6.22.3,
FFprobe arm64 e distribuição ExifTool 13.61 no computador de build.
