#!/bin/zsh
set -eu
cd "${0:A:h}"
export PATH="/opt/homebrew/bin:/usr/local/bin:/Library/Frameworks/Python.framework/Versions/Current/bin:$PATH"
trap 'echo "Se houve erro, confira docs/instalar-mac.md. Pressione Enter para fechar."; read -r' EXIT
python3 -c 'import sys, tkinter; assert sys.version_info >= (3,11), "Instale Python 3.11 ou superior com Tkinter"'
python3 -m venv .venv
.venv/bin/python -m pip install -e .
for tool in ffprobe exiftool; do
  command -v "$tool" >/dev/null || { echo "Falta $tool. Veja docs/instalar-mac.md."; exit 1; }
done
echo 'Instalado. Abra Abrir FujiTimeline.command nesta pasta.'
