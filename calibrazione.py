"""Regole personali ricavate in modo trasparente dal diario delle stampe."""
from collections import Counter
from statistics import median


CORREZIONI = {
    "si è staccata dal piatto": "Pulisci il piatto, controlla il primo strato e prova un brim più largo.",
    "angoli sollevati (warping)": "Riduci correnti d'aria, usa brim e verifica temperatura e pulizia del piatto.",
    "fili tra le parti (stringing)": "Asciuga il filamento e calibra temperatura e retrazione con un provino dedicato.",
    "supporti difficili da togliere": "Aumenta con piccoli passi la distanza Z o la spaziatura dell'interfaccia.",
    "superficie sotto i supporti ruvida": "Aumenta gli strati d'interfaccia e riduci la distanza Z con prudenza.",
    "strati che si separano": "Aumenta l'adesione tra layer: più temperatura, meno ventola o minore velocità.",
    "sporgenze cadenti": "Aumenta il raffreddamento, riduci la velocità delle sporgenze o abilita i supporti.",
    "pezzo poco rigido": "Aumenta prima le pareti; usa più riempimento solo se serve il volume interno.",
    "pezzo fragile": "Controlla orientamento degli strati, temperatura e pareti prima del riempimento.",
    "misure sbagliate": "Stampa un provino dimensionale e registra l'errore per asse prima di compensare.",
    "buchi o strati mancanti": "Controlla portata, ugello e trascinamento; poi calibra il flow.",
}


def _numeri(voci, campo, includi_zero=False):
    from validazione import numero
    return [float(v[campo]) for v in voci if numero(v.get(campo)) and (includi_zero or v[campo] != 0)]


def analizza(voci, materiale=None, soglia=2, profilo=None):
    """Riassume ricorrenze per materiale; suggerisce correzioni solo oltre la soglia scelta."""
    pertinenti = [v for v in voci if (not materiale or v.get("materiale") == materiale)
                  and (not profilo or (v.get("profilo_filamento") or "__non_annotato__") == profilo)]
    conteggi = Counter(p for v in pertinenti for p in v.get("problemi", []))
    ricorrenti = [{
        "problema": problema,
        "occorrenze": conteggio,
        "su_stampe": len(pertinenti),
        "correzione": CORREZIONI.get(problema, "Confronta le impostazioni delle stampe riuscite e fallite."),
    } for problema, conteggio in conteggi.most_common() if conteggio >= soglia]

    dimensionali = _numeri(pertinenti, "errore_dimensionale_mm", includi_zero=True)
    compensazione = None
    if len(dimensionali) >= soglia:
        errore = round(median(dimensionali), 3)
        compensazione = {
            "errore_mediano_mm": errore,
            "indicazione": f"Il pezzo risulta mediamente {abs(errore):g} mm "
                           + ("più grande" if errore > 0 else "più piccolo")
                           + "; conferma il dato per asse prima di compensare nello slicer.",
        }
        if errore == 0:
            compensazione["indicazione"] = "L'errore dimensionale mediano registrato è zero."

    riuscite = [v for v in pertinenti if v.get("esito") in ("buona", "ottima") and not v.get("problemi")]
    parametri = {}
    for campo, etichetta in (
        ("temperatura_ugello_c", "temperatura ugello °C"),
        ("temperatura_piatto_c", "temperatura piatto °C"),
        ("velocita_mm_s", "velocità mm/s"),
        ("flow_pct", "flow %"),
        ("retrazione_mm", "retrazione mm"),
    ):
        valori = _numeri(riuscite, campo)
        if valori:
            parametri[etichetta] = round(median(valori), 2)

    return {
        "materiale": materiale,
        "stampe_considerate": len(pertinenti),
        "dati_sufficienti": len(pertinenti) >= soglia,
        "problemi_osservati": dict(conteggi),
        "problemi_ricorrenti": ricorrenti,
        "compensazione_dimensionale": compensazione,
        "mediane_registrate": parametri,
        "stampe_riuscite": len(riuscite),
        "origine_correzioni": "Indicazioni predefinite per il difetto, non correlazioni apprese dai parametri.",
        "soglia_occorrenze": soglia,
        "limite": "Le correzioni derivano da ricorrenze annotate, non da un modello predittivo.",
    }


def materiale_da_profilo(nome_profilo, materiali):
    testo = (nome_profilo or "").lower()
    return next((m for m in sorted(materiali, key=len, reverse=True) if m.lower() in testo), None)
