"""Scritture atomiche e impronte dei dati usati nei calcoli."""
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path


def salva_json(percorso, dati):
    percorso = Path(percorso)
    percorso.parent.mkdir(parents=True, exist_ok=True)
    fd, temporaneo = tempfile.mkstemp(dir=percorso.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(dati, f, ensure_ascii=False, indent=2, allow_nan=False)
        for tentativo in range(9):
            try:
                os.replace(temporaneo, percorso)
                break
            except PermissionError:
                # Su Windows un lettore (dashboard/antivirus) può tenere aperto il file per pochi ms.
                if tentativo == 8:
                    raise
                time.sleep(min(.01 * 2 ** tentativo, .2))
    finally:
        if os.path.exists(temporaneo):
            os.unlink(temporaneo)


def impronta(dati):
    return hashlib.sha256(json.dumps(dati, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode("utf-8")).hexdigest()


def impronta_file(percorso):
    h = hashlib.sha256()
    with Path(percorso).open("rb") as f:
        for blocco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(blocco)
    return h.hexdigest()
