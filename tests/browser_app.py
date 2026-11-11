"""Avvia l'app reale con dati isolati e integrazioni esterne disabilitate."""
import os
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config
import augura_addon

data = Path(os.environ['STRATO_BROWSER_DATA'])
config.LAVORI = data / 'lavori'
config.FOTO = data / 'foto'
config.DIARIO = data / 'diario.jsonl'
config.BOBINE = data / 'bobine.json'
augura_addon.disponibile = lambda: False
runpy.run_path(str(ROOT / 'app.py'), run_name='__main__')
