@echo off
rem Installa l'add-on augura in un ambiente separato (circa 700 MB: build123d + OpenCASCADE).
rem Si può fare anche dalla barra laterale della dashboard.
cd /d "%~dp0.."
python augura_addon.py
echo.
echo Fatto. Se l'assistente è aperto, ricarica la pagina.
pause
