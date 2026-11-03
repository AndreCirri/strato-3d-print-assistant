"""Confronto tra varianti di processo sui migliori orientamenti."""
from validazione import numero as _numero, riga_valida
PESI_COMPROMESSO = {"tempo": .25, "materiale": .25, "layer": .25, "robustezza": .25}


def _materiale_g(risultato):
    campi = ("pezzo_g", "supporti_g", "brim_g")
    if not all(_numero(risultato.get(c)) for c in campi):
        return None
    return round(sum(float(risultato[c]) for c in campi), 2)


def _percentuale(valore, riferimento):
    if not _numero(valore) or not _numero(riferimento) or riferimento == 0:
        return None
    return round((valore - riferimento) / riferimento * 100, 1)


def _densita(riga):
    try:
        return float(str(riga.get("sparse_infill_density", "0")).rstrip("%"))
    except ValueError:
        return 0.0


def _indicatori(riga):
    return {
        "tempo": float(riga["tempo_s"]),
        "materiale": float(riga["materiale_g"]),
        "layer": float(riga["layer_height"]),
        "robustezza": float(riga["wall_loops"]) * 10 + _densita(riga),
    }


def frontiera_pareto(righe):
    """Candidati non dominati per tempo/materiale misurati e due indicatori dichiarati."""
    valide = [r for r in righe if riga_valida(r)]
    frontiera = []
    for candidata in valide:
        c = _indicatori(candidata)
        dominata = False
        for altra in valide:
            if altra is candidata:
                continue
            a = _indicatori(altra)
            non_peggiore = (a["tempo"] <= c["tempo"] and a["materiale"] <= c["materiale"]
                            and a["layer"] <= c["layer"] and a["robustezza"] >= c["robustezza"])
            strettamente_migliore = any((a[k] < c[k] for k in ("tempo", "materiale", "layer"))) \
                or a["robustezza"] > c["robustezza"]
            if non_peggiore and strettamente_migliore:
                dominata = True
                break
        if not dominata:
            frontiera.append({"orientamento_id": candidata["orientamento_id"],
                              "variante_id": candidata["variante_id"]})
    return frontiera


def alternative(righe):
    valide = [r for r in righe if riga_valida(r)]
    if not valide:
        return []

    def voce(obiettivo, riga, nota):
        return {"obiettivo": obiettivo, "orientamento_id": riga["orientamento_id"],
                "variante_id": riga["variante_id"], "variante": riga["variante"],
                "tempo": riga.get("tempo"), "materiale_g": riga.get("materiale_g"), "nota": nota}

    piu_veloce = min(valide, key=lambda r: (r["tempo_s"], r["materiale_g"]))
    meno_materiale = min(valide, key=lambda r: (r["materiale_g"], r["tempo_s"]))
    superficie = min(valide, key=lambda r: (float(r["layer_height"]),
                                             r.get("supporti_g") if _numero(r.get("supporti_g")) else float("inf"),
                                             r["tempo_s"]))
    robusta = max(valide, key=lambda r: (_indicatori(r)["robustezza"], -r["tempo_s"]))

    estremi = {k: (min(_indicatori(r)[k] for r in valide), max(_indicatori(r)[k] for r in valide))
               for k in ("tempo", "materiale", "layer", "robustezza")}
    def compromesso(riga):
        valori = _indicatori(riga)
        punteggi = []
        for k in ("tempo", "materiale", "layer"):
            minimo, massimo = estremi[k]
            punteggi.append((valori[k] - minimo) / (massimo - minimo) if massimo > minimo else 0)
        minimo, massimo = estremi["robustezza"]
        punteggi.append((massimo - valori["robustezza"]) / (massimo - minimo) if massimo > minimo else 0)
        return sum(p * PESI_COMPROMESSO[k] for p, k in zip(punteggi, PESI_COMPROMESSO))
    bilanciata = min(valide, key=lambda r: (compromesso(r), r["posizione_orientamento"]))

    return [
        voce("Più veloce", piu_veloce, "tempo misurato minimo"),
        voce("Meno materiale", meno_materiale, "grammi misurati minimi"),
        voce("Migliore superficie", superficie, "layer più fine; qualità attesa"),
        voce("Più robusta", robusta, "pareti e riempimento; robustezza attesa"),
        voce("Miglior compromesso", bilanciata, "distanza normalizzata dagli estremi"),
    ]


def scegli(righe, priorita):
    valide = [r for r in righe if riga_valida(r)]
    if not valide:
        return None

    p = (priorita or "").lower()
    if "veloc" in p:
        scelta = min(valide, key=lambda r: (r["tempo_s"], r["materiale_g"], r["posizione_orientamento"]))
        motivo = "è la combinazione con il tempo stimato più basso"
    elif "poco materiale" in p:
        scelta = min(valide, key=lambda r: (r["materiale_g"], r["tempo_s"], r["posizione_orientamento"]))
        motivo = "è la combinazione che usa meno materiale depositato"
    elif any(x in p for x in ("robustezza", "rigidità")):
        scelta = min(valide, key=lambda r: (-_indicatori(r)['robustezza'], r['posizione_orientamento'], r['tempo_s']))
        motivo = "la priorità richiede più pareti e più riempimento"
    elif any(x in p for x in ("superficie", "precisione")):
        scelta = min(valide, key=lambda r: (float(r['layer_height']), r['posizione_orientamento'], r['tempo_s']))
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
                for campo in ("tempo", "tempo_s", "pezzo_g", "supporti_g", "brim_g", "strati", "consumo_totale_g"):
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

    pareto = frontiera_pareto(righe)
    chiavi_pareto = {(p["orientamento_id"], p["variante_id"]) for p in pareto}
    for riga in righe:
        riga["pareto"] = (riga["orientamento_id"], riga["variante_id"]) in chiavi_pareto

    return {
        "priorita": priorita,
        "orientamenti_confrontati": [o["id"] for o in selezionati],
        "varianti": varianti,
        "risultati": righe,
        "frontiera_pareto": pareto,
        "criteri": {"pesi_compromesso": PESI_COMPROMESSO,
                    "robustezza": "10 × pareti + riempimento %; indicatore euristico, non resistenza misurata",
                    "superficie": "Altezza layer minore; indicatore euristico",
                    "normalizzazione": "Min-max sui candidati validi; pesi uguali del 25%"},
        "alternative": alternative(righe),
        "raccomandazione": scegli(righe, priorita),
    }


def aggiorna_priorita(ottimizzazione, priorita, meccanica=None):
    """Ricalcola la raccomandazione senza ripetere i sezionamenti."""
    ottimizzazione["priorita"] = priorita
    righe = ottimizzazione.get("risultati", [])
    pareto = frontiera_pareto(righe)
    chiavi_pareto = {(p["orientamento_id"], p["variante_id"]) for p in pareto}
    for riga in righe:
        riga["pareto"] = (riga["orientamento_id"], riga["variante_id"]) in chiavi_pareto
    ottimizzazione["frontiera_pareto"] = pareto
    ottimizzazione["alternative"] = alternative(righe)
    candidate = righe
    if meccanica and any(x in (priorita or "") for x in ("robustezza", "rigidità")):
        candidate = [r for r in righe if r["orientamento_id"] == meccanica["orientamento_consigliato"]
                     and int(r["wall_loops"]) >= meccanica["pareti_consigliate"]]
    ottimizzazione["raccomandazione"] = scegli(candidate, priorita)
    ottimizzazione["richiede_confronto_meccanico"] = bool(meccanica and not ottimizzazione["raccomandazione"])
    return ottimizzazione
