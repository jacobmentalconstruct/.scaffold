#!/usr/bin/env bash
set -e
echo "Setting up environment..."

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "Created virtual environment."
fi

source .venv/bin/activate
pip install -r requirements.txt
echo "Environment ready. Run: ./run.sh"
