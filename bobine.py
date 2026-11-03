"""Inventario locale delle bobine e stima del materiale disponibile."""
import json
import uuid
from pathlib import Path

import config


def tutte(percorso=None):
    percorso = Path(percorso or config.BOBINE)
    if not percorso.exists():
        return []
    return json.loads(percorso.read_text(encoding="utf-8"))


def _salva(voci, percorso=None):
    percorso = Path(percorso or config.BOBINE)
    percorso.write_text(json.dumps(voci, ensure_ascii=False, indent=2), encoding="utf-8")


def aggiungi(voce, percorso=None):
    voci = tutte(percorso)
    peso = max(0.0, float(voce["peso_netto_g"]))
    residuo = min(peso, max(0.0, float(voce.get("residuo_g", peso))))
    nuova = {
        "id": uuid.uuid4().hex[:8],
        "nome": voce.get("nome") or f"{voce['materiale']} {voce.get('colore', '')}".strip(),
        "materiale": voce["materiale"],
        "marca": voce.get("marca", ""),
        "colore": voce.get("colore", ""),
        "peso_netto_g": peso,
        "residuo_g": residuo,
        "tara_g": max(0.0, float(voce.get("tara_g", 0))),
        "costo_eur": max(0.0, float(voce.get("costo_eur", 0))),
        "stato": voce.get("stato", "pronta"),
    }
    voci.append(nuova)
    _salva(voci, percorso)
    return nuova


def aggiorna_residuo(identificativo, residuo_g, percorso=None):
    voci = tutte(percorso)
    voce = next(v for v in voci if v["id"] == identificativo)
    voce["residuo_g"] = min(float(voce["peso_netto_g"]), max(0.0, float(residuo_g)))
    if voce["residuo_g"] == 0:
        voce["stato"] = "esaurita"
    _salva(voci, percorso)
    return voce


def consuma(identificativo, grammi, percorso=None):
    voce = next(v for v in tutte(percorso) if v["id"] == identificativo)
    return aggiorna_residuo(identificativo, float(voce["residuo_g"]) - max(0.0, float(grammi)), percorso)


def aggiorna_da_pesata(identificativo, peso_lordo_g, percorso=None):
    voce = next(v for v in tutte(percorso) if v["id"] == identificativo)
    return aggiorna_residuo(identificativo, float(peso_lordo_g) - float(voce.get("tara_g", 0)), percorso)


def stime(voci, materiale, grammi_necessari):
    grammi = max(0.0, float(grammi_necessari))
    risultati = []
    for voce in voci:
        if materiale and voce.get("materiale") != materiale:
            continue
        peso = float(voce.get("peso_netto_g") or 0)
        costo = float(voce.get("costo_eur") or 0)
        residuo = float(voce.get("residuo_g") or 0)
        risultati.append({
            "id": voce["id"], "bobina": voce["nome"], "materiale": voce["materiale"],
            "residuo_g": round(residuo, 1), "sufficiente": residuo >= grammi,
            "margine_g": round(residuo - grammi, 1),
            "costo_stimato_eur": round(grammi * costo / peso, 2) if peso > 0 else None,
            "stato": voce.get("stato", "pronta"),
        })
    return sorted(risultati, key=lambda r: (not r["sufficiente"], r["stato"] != "pronta", r["residuo_g"]))
