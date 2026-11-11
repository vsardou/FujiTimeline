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
