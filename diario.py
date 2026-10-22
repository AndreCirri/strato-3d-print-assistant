"""Diario di stampa: una riga JSON per ogni stampa, così le esperienze si accumulano."""
import json
from datetime import datetime

import config

ESITI = ["ottima", "buona", "con difetti", "fallita"]
PROBLEMI = [
    "si è staccata dal piatto", "angoli sollevati (warping)", "fili tra le parti (stringing)",
    "supporti difficili da togliere", "superficie sotto i supporti ruvida", "strati che si separano",
    "sporgenze cadenti", "pezzo poco rigido", "pezzo fragile", "misure sbagliate", "buchi o strati mancanti",
]


def aggiungi(voce):
    voce = {"data": datetime.now().strftime("%Y-%m-%d %H:%M"), **voce}
    with config.DIARIO.open("a", encoding="utf-8") as f:
        f.write(json.dumps(voce, ensure_ascii=False) + "\n")
    return voce


def tutte():
    if not config.DIARIO.exists():
        return []
    return [json.loads(r) for r in config.DIARIO.read_text(encoding="utf-8").splitlines() if r.strip()]


def aggiorna(indice, campi):
    voci = tutte()
    voci[indice].update(campi)
    config.DIARIO.write_text("".join(json.dumps(v, ensure_ascii=False) + "\n" for v in voci), encoding="utf-8")
