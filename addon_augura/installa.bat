@echo off
rem Installa l'add-on augura in un ambiente separato (circa 700 MB: build123d + OpenCASCADE)
cd /d "%~dp0.."
if not exist .venv-augura python -m venv .venv-augura
.venv-augura\Scripts\python.exe -m pip install --upgrade pip
rem versione bloccata: augura è pre-alpha e l'interfaccia può cambiare tra le 0.1.x
.venv-augura\Scripts\python.exe -m pip install augura==0.1.8
echo.
echo Add-on installato. Riavvia l'assistente.
pause
