"""Add-on facoltativo: augura (https://github.com/pzfreo/augura), in un ambiente Python a parte.

Se l'ambiente .venv-augura non c'è, l'assistente funziona come prima. Se c'è:
- accetta file STEP (convertiti in STL con build123d per l'analisi e le immagini);
- aggiunge i controlli di augura: esatti sugli STEP (ponti, spessori, orientamenti),
  approssimati sugli STL.
"""
import json
import subprocess
import tempfile
from pathlib import Path

import config

VENV = config.CARTELLA / ".venv-augura"
PYTHON = VENV / "Scripts" / "python.exe"
AUGURA = VENV / "Scripts" / "augura.exe"
PONTE = config.CARTELLA / "addon_augura" / "ponte.py"
FORMATI_STEP = {".step", ".stp"}


def disponibile():
    return PYTHON.exists() and AUGURA.exists()


def _esegui(comando, timeout=600):
    # cartella di lavoro neutra: niente file del progetto nella directory corrente del sottoprocesso
    r = subprocess.run([str(c) for c in comando], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout, cwd=tempfile.gettempdir())
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[-800:] or f"uscita {r.returncode}")
    return r.stdout


def step_in_stl(step, stl):
    _esegui([PYTHON, PONTE, "step2stl", step, stl])


def _json(comando):
    return json.loads(_esegui(comando))


def verifica(percorso):
    """Controlli di augura sul file così com'è orientato; per gli STEP anche gli orientamenti."""
    percorso = Path(percorso)
    esatto = percorso.suffix.lower() in FORMATI_STEP
    comuni = ["--nozzle", config.UGELLO_MM, "--build-volume", *config.VOLUME_STAMPA]
    out = {"geometria": "esatta (STEP)" if esatto else "approssimata (STL: niente ponti né orientamenti)",
           "errori": []}
    try:
        out["controlli_come_nel_file"] = _json([AUGURA, "analyze", percorso, "--format", "json", *comuni])["findings"]
    except Exception as e:
        out["errori"].append(f"analyze: {e}")
    if esatto:
        try:
            migliore = _json([AUGURA, "analyze", percorso, "--format", "json", "--best-orientation", *comuni])
            out["controlli_orientamento_migliore"] = migliore
        except Exception as e:
            out["errori"].append(f"best-orientation: {e}")
        try:
            ori = _json([AUGURA, "orientations", percorso, "--format", "json",
                         "--build-volume", *config.VOLUME_STAMPA])["orientations"]
            out["orientamenti"] = ori[:8]
            out["nota_orientamenti"] = "rotation = angoli di Eulero X, Y, Z in gradi rispetto al file"
        except Exception as e:
            out["errori"].append(f"orientations: {e}")
    return out
