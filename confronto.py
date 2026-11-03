"""Confronto riprendibile dei processi, condiviso da dashboard e worker."""
from pathlib import Path
from copy import deepcopy
import config
import classifica
import ottimizzazione
import resistenza
import slicer_cli
import ricerca
from persistenza import impronta, salva_json


def meccanica(dati, richiesta):
    return resistenza.valuta(dati["orientamenti"], richiesta.get("direzione_carico"),
                             richiesta.get("sollecitazione", "non specificata"),
                             richiesta.get("parte_critica", "nessuna indicata"), dati.get("spessori"),
                             [richiesta.get('fissaggio_' + k, 0) for k in 'xyz'] if richiesta.get('usa_punti_carico') else None,
                             [richiesta.get('carico_' + k, 0) for k in 'xyz'] if richiesta.get('usa_punti_carico') else None,
                             richiesta.get('vincoli', ''), richiesta.get('zona_critica', ''))


def firma(modello, dati, richiesta):
    sez = dati.get("sezionamento", {})
    m, p, f = slicer_cli.profili(sez.get("processo", config.PROFILO_PROCESSO),
                                sez.get("filamento", config.PROFILO_FILAMENTO),
                                sez.get("supporti", config.SUPPORTI_SEZIONAMENTO))
    return impronta({"calcolo": slicer_cli.contesto(modello, m, p, f),
                     "geometria": config.VERSIONE_GEOMETRIA,
                     "ricerca": [ricerca.VERSIONE, richiesta.get('budget_ricerca', 4), richiesta.get('priorita')],
                     "varianti": config.VARIANTI_PROCESSO,
                     "selezionati": [o["id"] for o in dati["orientamenti"][:config.NUM_ORIENTAMENTI_VARIANTI]],
                     "meccanica": meccanica(dati, richiesta) if richiesta.get("priorita") == "robustezza e rigidità" else None})


def calcola(mesh, dati, cartella, richiesta, avanzamento=None):
    sez = dati.get("sezionamento", {})
    processo = sez.get("processo", config.PROFILO_PROCESSO)
    filamento = sez.get("filamento", config.PROFILO_FILAMENTO)
    supporti = sez.get("supporti", config.SUPPORTI_SEZIONAMENTO)
    varianti = deepcopy(config.VARIANTI_PROCESSO)
    base = slicer_cli.profilo(processo, supporti)
    for variante in varianti:
        if variante.get("riferimento"):
            variante["impostazioni"] = {k: base[k] for k in variante["impostazioni"]}
    # Ricalcola o verifica tutti i riferimenti prima di scegliere i migliori orientamenti.
    slicer_cli.seziona_orientamenti(mesh, dati["orientamenti"], cartella / "sezionamenti", processo,
                                    filamento, supporti)
    classifica.applica(dati)
    selezionati = list(dati["orientamenti"][:config.NUM_ORIENTAMENTI_VARIANTI])
    mec = meccanica(dati, richiesta)
    if mec and richiesta.get("priorita") == "robustezza e rigidità":
        preferito = next(o for o in dati["orientamenti"] if o["id"] == mec["orientamento_consigliato"])
        selezionati = [preferito] + [o for o in selezionati if o["id"] != preferito["id"]]
        varianti.append({"id": "meccanico", "nome": "Meccanico", "descrizione": "Carico dichiarato",
                         "impostazioni": {"layer_height": "0.16", "wall_loops": str(mec["pareti_consigliate"]),
                                          "sparse_infill_density": "25%"}})
    # La cache controlla i dati completi; il primo passaggio dopo l'aggiornamento può richiedere un ricalcolo.
    extra = slicer_cli.seziona_varianti(mesh, selezionati, cartella / "varianti", processo,
                                       filamento, varianti, avanzamento, supporti=supporti)
    opt = ottimizzazione.costruisci(selezionati, varianti, extra, richiesta.get("priorita"), len(selezionati))
    budget = max(0, min(8, int(richiesta.get('budget_ricerca', 4))))
    for passo in range(budget):
        proposta = ricerca.proponi(opt['risultati'], varianti, richiesta.get('priorita'), mec)
        if proposta is None:
            break
        oid, variante = proposta
        orientamento = next(o for o in selezionati if o['id'] == oid)
        if not any(v['id'] == variante['id'] for v in varianti):
            varianti.append(variante)
        if avanzamento:
            avanzamento(passo, orientamento, variante, budget)
        extra += slicer_cli.seziona_varianti(mesh, [orientamento], cartella / 'varianti', processo,
                                            filamento, [variante], supporti=supporti)
        # Le varianti locali non vengono misurate su tutti gli orientamenti: conserva solo le coppie provate.
        completo = ottimizzazione.costruisci(selezionati, varianti, extra, richiesta.get('priorita'), len(selezionati))
        tentate = {(r['orientamento_id'], r['variante_id']) for r in extra}
        completo['risultati'] = [r for r in completo['risultati']
                                  if (r['orientamento_id'], r['variante_id']) in tentate or r['variante_id'] == 'bilanciato']
        opt = completo
        ottimizzazione.aggiorna_priorita(opt, richiesta.get('priorita'), mec)
        opt['ricerca'] = {'prove_aggiuntive': passo + 1, 'budget': budget, 'metodo': 'vicini del migliore, una modifica alla volta'}
        dati['ottimizzazione_processo'] = opt
        salva_json(cartella / 'analisi.json', dati)
    ottimizzazione.aggiorna_priorita(opt, richiesta.get("priorita"), mec)
    dati["ottimizzazione_processo"] = opt
    classifica.applica(dati)
    opt["firma"] = firma(cartella / Path(dati["file"]).name, dati, richiesta)
    return dati
