#!/bin/bash
# Wrapper script to run ammo-atom parser with virtual environment activated

cd "$(dirname "$0")" || exit 1

# Activate virtual environment and run parser
source .venv/bin/activate && python3 ./source/ammo-atom/__main__.py "$@"
