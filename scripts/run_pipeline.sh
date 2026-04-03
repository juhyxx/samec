#!/usr/bin/env bash
set -euo pipefail

# run_pipeline.sh
# Usage: ./scripts/run_pipeline.sh [--no-ocr] [--no-resolve] [--serve PORT]
# By default: creates venv, installs deps, runs extract_catalog.py, parse_rows.py, resolve_definitions.py

VENV_DIR="venv"
PY="$VENV_DIR/bin/python3"
PIP="$VENV_DIR/bin/pip"
INSTALL=true
RUN_OCR=true
RUN_RESOLVE=true
SERVE_PORT=0

show_help(){
  cat <<EOF
Usage: $0 [options]

Options:
  --no-install      Skip creating venv and installing packages
  --no-ocr          Skip OCR + swatch extraction (extract_catalog.py)
  --no-resolve      Skip RAL/FS resolution (resolve_definitions.py)
  --serve PORT      Start a simple HTTP server after processing (port default 8000)
  --help            Show this help

Examples:
  $0                # setup venv, install, run full pipeline
  $0 --no-ocr       # skip heavy OCR step
  $0 --serve 8000   # run pipeline and serve files
EOF
}

# parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-install) INSTALL=false; shift ;;
    --no-ocr) RUN_OCR=false; shift ;;
    --no-resolve) RUN_RESOLVE=false; shift ;;
    --serve) SERVE_PORT=${2:-8000}; shift 2 ;;
    --help) show_help; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; show_help; exit 2 ;;
  esac
done

# Ensure Python exists
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found. Install Python 3 and retry." >&2
  exit 1
fi

# Create venv and install
if [ "$INSTALL" = true ]; then
  if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtualenv in $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
  fi
  echo "Activating venv and installing requirements..."
  # Use pip inside venv
  "$PIP" install --upgrade pip
  if [ -f requirements.txt ]; then
    "$PIP" install -r requirements.txt
  fi
  # ensure our additional deps
  "$PIP" install easyocr opencv-python-headless scikit-image torch torchvision || true
fi

# Helper to run script using venv python
run_py(){
  if [ ! -x "$PY" ]; then
    echo "Virtualenv python not found at $PY" >&2
    exit 1
  fi
  echo "-> Running: $*"
  "$PY" "$@"
}

# Run OCR+swatch extraction
if [ "$RUN_OCR" = true ]; then
  if [ -f source/extract_catalog.py ]; then
    run_py source/extract_catalog.py
  else
    echo "source/extract_catalog.py not found, skipping OCR step" >&2
  fi
else
  echo "Skipping OCR step (--no-ocr)"
fi

# Parse rows
if [ -f source/parse_rows.py ]; then
  run_py source/parse_rows.py
else
  echo "source/parse_rows.py not found, skipping parse step" >&2
fi

# Resolve definitions to hex
if [ "$RUN_RESOLVE" = true ]; then
  if [ -f source/resolve_definitions.py ]; then
    run_py source/resolve_definitions.py
  else
    echo "source/resolve_definitions.py not found, skipping resolve step" >&2
  fi
else
  echo "Skipping resolve step (--no-resolve)"
fi

# Summary
echo "\nPipeline finished. Outputs:"
ls -la data | sed -n '1,200p' || true

# Serve if requested
if [ "$SERVE_PORT" -ne 0 ]; then
  PORT=${SERVE_PORT:-8000}
  echo "Starting HTTP server at http://localhost:$PORT"
  (cd . && "$PY" -m http.server "$PORT")
fi
