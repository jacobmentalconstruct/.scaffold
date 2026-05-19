@echo off
echo Setting up environment...

if not exist .venv (
    python -m venv .venv
    echo Created virtual environment.
)

call .venv\Scripts\activate.bat
pip install -r requirements.txt
echo Environment ready. Run: run.bat
