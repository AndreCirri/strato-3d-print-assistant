"""Classifica gli orientamenti usando i risultati reali dello slicer.

Il profilo abituale genera supporti solo dal piatto. I grammi del G-code sono quindi
il dato principale, ma non descrivono le sporgenze che richiederebbero un supporto
appoggiato sul pezzo: per quelle resta necessaria la stima geometrica.
"""

GRAMMI_PER_1000_MM2 = 5.0
GRAMMI_PER_MM2 = GRAMMI_PER_1000_MM2 / 1000
PESO_SUPPORTI_SUL_PEZZO = 3.0
PESO_BRIM = 0.25


def _numero(valore):
    return isinstance(valore, (int, float)) and not isinstance(valore, bool)


def punteggio_geometrico(orientamento):
    """Legge il punteggio nuovo o quello delle analisi salvate prima della modifica."""
    return orientamento.get("punteggio_geometrico", orientamento.get("punteggio"))


def calcola_punteggio_reale(orientamento):
    """Aggiunge le componenti del punteggio reale; False se il sezionamento non è valido."""
    slicer = orientamento.get("slicer") or {}
    supporti_g = slicer.get("supporti_g")
    if not _numero(supporti_g) or "errore" in slicer:
        for campo in ("supporti_sul_pezzo_stimati_g", "supporti_equivalenti_g",
                      "penalita_stabilita_reale_g", "punteggio_reale"):
            orientamento.pop(campo, None)
        return False

    area_sul_pezzo = max(0.0, float(orientamento.get("supporti_sul_pezzo_area_mm2") or 0))
    brim_g = max(0.0, float(slicer.get("brim_g") or 0))
    penalita_geometrica = max(0.0, float(orientamento.get("penalita_stabilita") or 0))

    # 5 g/1000 mm² è la mediana osservata sui lavori già sezionati. Queste superfici
    # non sono comprese nei grammi reali perché il profilo crea supporti solo dal piatto.
    supporti_sul_pezzo_g = area_sul_pezzo * GRAMMI_PER_MM2
    penalita_stabilita_g = penalita_geometrica * GRAMMI_PER_MM2
    supporti_equivalenti_g = float(supporti_g) + PESO_SUPPORTI_SUL_PEZZO * supporti_sul_pezzo_g
    totale = supporti_equivalenti_g + PESO_BRIM * brim_g + penalita_stabilita_g

    orientamento.update({
        "supporti_sul_pezzo_stimati_g": round(supporti_sul_pezzo_g, 2),
        "supporti_equivalenti_g": round(supporti_equivalenti_g, 2),
        "penalita_stabilita_reale_g": round(penalita_stabilita_g, 2),
        "punteggio_reale": round(totale, 2),
    })
    return True


def _aggiorna_confronto_slicer(dati):
    confronto = dati.get("confronto_slicer")
    orientamenti = dati.get("orientamenti", [])
    if not confronto or not orientamenti:
        return
    primo = orientamenti[0]
    confronto["id_primo_nostra_classifica"] = primo.get("id")
    per_id = {o.get("id"): o for o in orientamenti}
    campi = [
        "altezza_mm", "area_appoggio_mm2", "supporti_dal_piatto_area_mm2",
        "supporti_sul_pezzo_area_mm2", "si_ribalta", "brim_consigliato",
        "punteggio_geometrico", "punteggio_reale", "costo_slicer",
    ]
    for scelta in confronto.get("scelte", []):
        suo = per_id.get(scelta.get("id"))
        if not suo:
            continue
        score_suo = suo.get("punteggio_reale")
        score_primo = primo.get("punteggio_reale")
        if score_primo is None:
            score_suo = punteggio_geometrico(suo)
            score_primo = punteggio_geometrico(primo)
        concorda = suo is primo or (_numero(score_suo) and _numero(score_primo) and score_suo <= score_primo)
        scelta["concorda_con_nostra_classifica"] = concorda
        scelta["differenze"] = {} if concorda else {
            campo: {"slicer": suo.get(campo), "nostro_primo": primo.get(campo)}
            for campo in campi if suo.get(campo) != primo.get(campo)
        }


def applica(dati):
    """Annota e ordina in-place gli orientamenti, senza mai cambiare i loro ID."""
    orientamenti = dati.get("orientamenti", [])
    if not orientamenti:
        return dati

    for o in orientamenti:
        geometrico = punteggio_geometrico(o)
        if geometrico is not None:
            o["punteggio_geometrico"] = geometrico
        calcola_punteggio_reale(o)

    geometrici = sorted(orientamenti, key=lambda o: (punteggio_geometrico(o) is None,
                                                      punteggio_geometrico(o)
                                                      if punteggio_geometrico(o) is not None else 0,
                                                      o.get("id", 0)))
    for posizione, o in enumerate(geometrici, 1):
        o["posizione_geometrica"] = posizione

    reali = [o for o in orientamenti if _numero(o.get("punteggio_reale"))]
    if reali:
        orientamenti.sort(key=lambda o: (not _numero(o.get("punteggio_reale")),
                                         o.get("punteggio_reale", float("inf")),
                                         punteggio_geometrico(o) if punteggio_geometrico(o) is not None
                                         else float("inf"), o.get("id", 0)))
        for posizione, o in enumerate(orientamenti, 1):
            o["posizione_reale"] = posizione if _numero(o.get("punteggio_reale")) else None
        dati["classifica"] = {
            "metodo": "sezionamento_reale",
            "unita": "g equivalenti di supporto",
            "formula": "supporti reali + 3 × supporti sul pezzo stimati + 0,25 × brim + penalità stabilità",
            "grammi_stimati_per_1000_mm2": GRAMMI_PER_1000_MM2,
            "orientamenti_sezionati": len(reali),
            "orientamenti_totali": len(orientamenti),
        }
    else:
        orientamenti[:] = geometrici
        for o in orientamenti:
            o["posizione_reale"] = None
        dati["classifica"] = {"metodo": "geometria", "unita": "indice geometrico"}

    _aggiorna_confronto_slicer(dati)
    return dati
