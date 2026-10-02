#!/bin/zsh
set -eu
cd "${0:A:h}"
if [[ ! -x .venv/bin/python ]]; then
  print 'Install the development environment first. See README.md.'
  read '?Press Return to close.'
  exit 1
fi
exec .venv/bin/python run_studio.py
