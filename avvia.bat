@echo off
rem Avvia l'assistente di stampa e apre il browser
cd /d "%~dp0"
start "" http://localhost:8501
python -m streamlit run app.py
