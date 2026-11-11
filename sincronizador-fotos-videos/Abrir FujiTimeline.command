#!/bin/zsh
set -eu
cd "${0:A:h}"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
if [[ ! -x .venv/bin/python ]]; then
  echo 'Execute primeiro Instalar no Mac.command. Pressione Enter para fechar.'
  read -r
  exit 1
fi
exec .venv/bin/python -m fujitimeline.gui
