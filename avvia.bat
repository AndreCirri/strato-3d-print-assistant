@echo off
rem Avvia l'assistente di stampa e apre il browser
cd /d "%~dp0"
if not exist .venv (
  python -m venv .venv
  .venv\Scripts\python.exe -m pip install -r requirements.txt
)
start "" http://localhost:8501
.venv\Scripts\python.exe -m streamlit run app.py
