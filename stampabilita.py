"""Controlli strutturati di stampabilità ricavati da geometria e sezionamento."""


ORDINE_GRAVITA = {"errore": 0, "avviso": 1, "info": 2}


def _aggiungi(risultati, codice, gravita, controllo, messaggio, azione, orientamento_id=None):
    risultati.append({
        "codice": codice,
        "gravita": gravita,
        "controllo": controllo,
        "orientamento_id": orientamento_id,
        "messaggio": messaggio,
        "azione": azione,
    })


def valuta(dati, volume_stampa=(256, 256, 256), ugello_mm=0.4):
    """Restituisce problemi verificabili e rischi euristici per il primo orientamento."""
    risultati = []
    dimensioni = dati.get("dimensioni_mm") or []
    if len(dimensioni) == 3 and any(float(d) > float(limite)
                                    for d, limite in zip(sorted(dimensioni), sorted(volume_stampa))):
        _aggiungi(risultati, "fuori_volume", "errore", "Volume di stampa",
                  f"Il pezzo misura {' × '.join(f'{d:g}' for d in dimensioni)} mm e non entra nel volume configurato.",
                  "Ruota o dividi il modello prima di sezionarlo.")

    if not dati.get("chiuso_stagno", True):
        _aggiungi(risultati, "mesh_aperta", "avviso", "Mesh aperta",
                  f"Sono presenti {dati.get('bordi_aperti', '?')} bordi aperti.",
                  "Controlla la riparazione automatica nell'anteprima dello slicer.")
    if (dati.get("corpi_separati") or 1) > 1:
        _aggiungi(risultati, "corpi_separati", "avviso", "Corpi separati",
                  f"Il file contiene {dati['corpi_separati']} corpi distinti.",
                  "Verifica che ogni corpo inizi sul piatto o su materiale già stampato.")

    spessori = dati.get("spessori") or {}
    sottili = spessori.get("area_sotto_0_8mm_pct")
    if isinstance(sottili, (int, float)) and sottili > 0:
        gravita = "errore" if sottili >= 10 else "avviso"
        _aggiungi(risultati, "pareti_sottili", gravita, "Pareti sottili",
                  f"Circa il {sottili:g}% delle pareti misurate è sotto {2 * ugello_mm:g} mm.",
                  "Controlla l'anteprima delle pareti e abilita le pareti sottili solo se il dettaglio resta stampabile.")

    orientamenti = dati.get("orientamenti") or []
    if orientamenti:
        migliore = orientamenti[0]
        oid = migliore.get("id")
        if migliore.get("si_ribalta"):
            _aggiungi(risultati, "ribaltamento", "errore", "Stabilità",
                      "Il baricentro cade fuori dall'area di appoggio nell'orientamento consigliato.",
                      "Scegli un altro orientamento oppure usa supporti e brim adeguati.", oid)
        rapporto = migliore.get("rapporto_altezza_appoggio")
        if isinstance(rapporto, (int, float)) and rapporto > 4:
            _aggiungi(risultati, "pezzo_slanciato", "avviso", "Rischio urto dell'ugello",
                      f"Il rapporto tra altezza e appoggio è {rapporto:g}: il pezzo è slanciato.",
                      "Usa brim, riduci accelerazioni e controlla che l'ugello non urti le parti già stampate.", oid)
        supporto_pezzo = float(migliore.get("supporti_sul_pezzo_area_mm2") or 0)
        if supporto_pezzo > 0:
            _aggiungi(risultati, "supporti_sul_pezzo", "avviso", "Rimozione dei supporti",
                      f"Circa {supporto_pezzo:g} mm² di sporgenze richiedono supporti appoggiati sul pezzo.",
                      "Controlla accessibilità e finitura delle superfici di contatto.", oid)
        supporti_alti = float(migliore.get("altezza_max_supporti_mm") or 0)
        if supporti_alti > 50:
            _aggiungi(risultati, "supporti_alti", "avviso", "Supporti alti",
                      f"I supporti stimati raggiungono {supporti_alti:g} mm di altezza.",
                      "Valuta un orientamento che accorci i supporti o aumenta la loro stabilità.", oid)
        slicer = migliore.get("slicer") or {}
        pezzo_g, supporti_g = slicer.get("pezzo_g"), slicer.get("supporti_g")
        if isinstance(pezzo_g, (int, float)) and isinstance(supporti_g, (int, float)) and pezzo_g > 0:
            rapporto_supporti = supporti_g / pezzo_g
            if rapporto_supporti > 0.4:
                _aggiungi(risultati, "molti_supporti", "avviso", "Quantità di supporti",
                          f"I supporti pesano il {rapporto_supporti * 100:.0f}% del pezzo.",
                          "Confronta gli altri orientamenti prima di accettare questo consumo.", oid)
        if migliore.get("brim_consigliato"):
            _aggiungi(risultati, "brim", "info", "Adesione al piatto",
                      migliore.get("brim_motivo") or "L'appoggio richiede un brim.",
                      "Mantieni il brim nel profilo esportato e controlla il primo strato.", oid)

    risultati.sort(key=lambda r: (ORDINE_GRAVITA[r["gravita"]], r["controllo"]))
    dettaglio = dati.get('controlli_dettagliati') or {}
    geometria = dettaglio.get('geometria') or {}
    percorso = dettaglio.get('toolpath') or {}
    oid = dettaglio.get('orientamento_id')
    isole = list(percorso.get('isole_senza_appoggio', []))
    if not percorso or percorso.get('limitato') or percorso.get('archi_non_analizzati'):
        isole += geometria.get('isole_geometriche', [])
    verifiche = [
        (geometria.get('cavita_chiuse'), 'cavita_chiuse', 'Cavità chiuse', 'Zone libere senza collegamento all’esterno nelle sezioni.', 'Valuta di aprire o dividere il modello.'),
        (geometria.get('zone_inaccessibili_utensile_2mm'), 'accesso', 'Accesso ai supporti', 'Zone non raggiungibili da un utensile di diametro 2 mm.', 'Controlla la possibilità di estrarre i supporti.'),
        (geometria.get('campioni_supporto_in_cavita_chiuse'), 'supporti_interni', 'Supporti in cavità chiuse', 'Campioni di supporto del G-code ricadono in cavità chiuse dopo allineamento stimato.', 'Conferma la posizione nel toolpath e valuta di dividere il modello.'),
        (geometria.get('fori_piccoli'), 'fori', 'Fori e canali piccoli', 'Sezioni di fori/canali più strette di quattro diametri ugello.', 'Verifica la quota e calibra la compensazione dei fori.'),
        (geometria.get('ponti'), 'ponti', 'Ponti', 'Rilevate superfici con appoggi sui due lati; luce e direzione sono nella tabella dettagliata.', 'Orienta le linee di ponte lungo la luce supportata e verifica il raffreddamento.'),
        (isole, 'isole', 'Isole senza appoggio', 'Nuove regioni senza appoggio rilevato alla risoluzione del controllo.', 'Verifica supporti o dividi il modello.'),
        (percorso.get('collisioni'), 'collisioni', 'Attraversamenti del materiale', 'Spostamenti dell’ugello sotto la quota di materiale già depositato.', 'Controlla Z-hop e traiettorie di viaggio.'),
    ]
    for presente, codice, nome, messaggio, azione in verifiche:
        if presente:
            quantita = len(presente) if isinstance(presente, list) else presente
            _aggiungi(risultati, codice, 'avviso', nome, f'{messaggio} Rilevamenti: {quantita}.', azione, oid)
    if percorso.get('percorsi_disconnessi'):
        _aggiungi(risultati, 'percorsi', 'info', 'Percorsi separati',
                  'Il G-code contiene regioni disconnesse nello stesso strato; possono essere intenzionali.',
                  'Verifica che corrispondano a parti previste.', oid)
    risultati.sort(key=lambda r: (ORDINE_GRAVITA[r['gravita']], r['controllo']))
    return {
        "orientamento_valutato": orientamenti[0].get("id") if orientamenti else None,
        "controlli": risultati,
        "errori": sum(r["gravita"] == "errore" for r in risultati),
        "avvisi": sum(r["gravita"] == "avviso" for r in risultati),
        "limiti": [
            "Supporti intrappolati e collisioni sono rischi geometrici: vanno confermati nell'anteprima del toolpath.",
            "Fori e giochi dimensionali richiedono quote nominali o un file CAD per essere valutati con precisione.",
        ],
    }
