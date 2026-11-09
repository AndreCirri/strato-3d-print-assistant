@echo off
setlocal
if not defined FIGCRAFT_EXE set "FIGCRAFT_EXE=%ProgramFiles%\ArtCraft\FigCraft\figcraft.exe"
if not exist "%FIGCRAFT_EXE%" set "FIGCRAFT_EXE=%LocalAppData%\Programs\ArtCraft\FigCraft\figcraft.exe"
if not exist "%FIGCRAFT_EXE%" (
  echo FigCraft non trovato. Imposta FIGCRAFT_EXE al percorso completo di figcraft.exe.
  pause
  exit /b 1
)
start "" "%FIGCRAFT_EXE%" --control 7979 "%~dp0strato-ui.figcraft"
endlocal
