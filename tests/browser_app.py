"""Avvio browser su dati isolati: STRATO_BROWSER_DATA deve indicare una cartella di test."""
import os
from pathlib import Path
import runpy
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config

cartella = Path(os.environ["STRATO_BROWSER_DATA"]).resolve()
cartella.mkdir(parents=True, exist_ok=True)
config.LAVORI = cartella / "lavori"
config.FOTO = cartella / "foto"
config.DIARIO = cartella / "diario.jsonl"
config.BOBINE = cartella / "bobine.json"

runpy.run_path(str(config.CARTELLA / "app.py"), run_name="__main__")
