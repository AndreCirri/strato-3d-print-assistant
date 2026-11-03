"""Confronto tra varianti di processo sui migliori orientamenti."""


def _numero(valore):
    return isinstance(valore, (int, float)) and not isinstance(valore, bool)


def _materiale_g(risultato):
    campi = ("pezzo_g", "supporti_g", "brim_g")
    if not all(_numero(risultato.get(c)) for c in campi):
        return None
    return round(sum(float(risultato[c]) for c in campi), 2)


def _percentuale(valore, riferimento):
    if not _numero(valore) or not _numero(riferimento) or riferimento == 0:
        return None
    return round((valore - riferimento) / riferimento * 100, 1)


def scegli(righe, priorita):
    valide = [r for r in righe if not r.get("errore") and _numero(r.get("tempo_s"))
              and _numero(r.get("materiale_g"))]
    if not valide:
        return None

    p = (priorita or "").lower()
    if "veloc" in p:
        scelta = min(valide, key=lambda r: (r["tempo_s"], r["materiale_g"], r["posizione_orientamento"]))
        motivo = "è la combinazione con il tempo stimato più basso"
    elif "poco materiale" in p:
        scelta = min(valide, key=lambda r: (r["materiale_g"], r["tempo_s"], r["posizione_orientamento"]))
        motivo = "è la combinazione che usa meno materiale depositato"
    elif any(x in p for x in ("superficie", "precisione", "robustezza", "rigidità")):
        preferite = [r for r in valide if r["variante_id"] == "dettaglio"] or valide
        scelta = min(preferite, key=lambda r: (r["posizione_orientamento"], r["tempo_s"]))
        motivo = "la priorità richiede strati fini, tre pareti e più riempimento"
    else:
        preferite = [r for r in valide if r["variante_id"] == "bilanciato"] or valide
        scelta = min(preferite, key=lambda r: (r["posizione_orientamento"], r["tempo_s"]))
        motivo = "mantiene il profilo abituale sul miglior orientamento"
    return {
        "orientamento_id": scelta["orientamento_id"],
        "variante_id": scelta["variante_id"],
        "variante": scelta["variante"],
        "motivo": motivo,
    }


def costruisci(orientamenti, varianti, risultati_extra, priorita, massimo_orientamenti=2):
    """Crea una struttura JSON con risultati, delta e raccomandazione.

    Il risultato della variante di riferimento viene preso da ``orientamento['slicer']``;
    gli altri arrivano da ``risultati_extra`` come lista di record.
    """
    selezionati = orientamenti[:massimo_orientamenti]
    extra = {(r["orientamento_id"], r["variante_id"]): r["risultato"] for r in risultati_extra}
    righe = []
    for posizione, o in enumerate(selezionati, 1):
        temporanee = []
        for variante in varianti:
            risultato = ((o.get("slicer") or {}) if variante.get("riferimento") else
                         extra.get((o["id"], variante["id"]), {"errore": "risultato mancante"}))
            riga = {
                "orientamento_id": o["id"],
                "posizione_orientamento": posizione,
                "variante_id": variante["id"],
                "variante": variante["nome"],
                "descrizione": variante["descrizione"],
                **variante["impostazioni"],
            }
            if "errore" in risultato:
                riga["errore"] = risultato["errore"]
            else:
                for campo in ("tempo", "tempo_s", "pezzo_g", "supporti_g", "brim_g", "strati"):
                    riga[campo] = risultato.get(campo)
                riga["materiale_g"] = _materiale_g(risultato)
            temporanee.append(riga)

        riferimento = next((r for r, v in zip(temporanee, varianti) if v.get("riferimento")), None)
        for riga in temporanee:
            if riferimento and not riga.get("errore") and not riferimento.get("errore"):
                riga["delta_tempo_pct"] = _percentuale(riga.get("tempo_s"), riferimento.get("tempo_s"))
                riga["delta_materiale_pct"] = _percentuale(riga.get("materiale_g"),
                                                             riferimento.get("materiale_g"))
            righe.append(riga)

    return {
        "priorita": priorita,
        "orientamenti_confrontati": [o["id"] for o in selezionati],
        "varianti": varianti,
        "risultati": righe,
        "raccomandazione": scegli(righe, priorita),
    }


def aggiorna_priorita(ottimizzazione, priorita):
    """Ricalcola la raccomandazione senza ripetere i sezionamenti."""
    ottimizzazione["priorita"] = priorita
    ottimizzazione["raccomandazione"] = scegli(ottimizzazione.get("risultati", []), priorita)
    return ottimizzazione
