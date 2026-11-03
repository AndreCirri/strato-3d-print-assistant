"""Confronto riprendibile dei processi, condiviso da dashboard e worker."""
from pathlib import Path
from copy import deepcopy
import config
import classifica
import ottimizzazione
import resistenza
import slicer_cli
from persistenza import impronta


def meccanica(dati, richiesta):
    return resistenza.valuta(dati["orientamenti"], richiesta.get("direzione_carico"),
                             richiesta.get("sollecitazione", "non specificata"),
                             richiesta.get("parte_critica", "nessuna indicata"), dati.get("spessori"))


def firma(modello, dati, richiesta):
    sez = dati.get("sezionamento", {})
    m, p, f = slicer_cli.profili(sez.get("processo", config.PROFILO_PROCESSO),
                                sez.get("filamento", config.PROFILO_FILAMENTO),
                                sez.get("supporti", config.SUPPORTI_SEZIONAMENTO))
    return impronta({"calcolo": slicer_cli.contesto(modello, m, p, f),
                     "geometria": config.VERSIONE_GEOMETRIA,
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
    ottimizzazione.aggiorna_priorita(opt, richiesta.get("priorita"), mec)
    dati["ottimizzazione_processo"] = opt
    classifica.applica(dati)
    opt["firma"] = firma(cartella / Path(dati["file"]).name, dati, richiesta)
    return dati
