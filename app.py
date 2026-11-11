"""Assistente di stampa 3D. Avvio:  streamlit run app.py

analisi e render (trimesh, matplotlib) si importano solo quando si analizza un pezzo:
caricarli all'avvio costava più di dieci secondi prima che comparisse la pagina."""
import hashlib
import json
import re
from datetime import datetime
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

import augura_addon
import bobine
import calibrazione
import classifica
import config
import diario
import ottimizzazione
import orienta_slicer
import resistenza
import slicer_cli
import stampabilita
import lavorazioni
import confronto
from persistenza import salva_json
from validazione import riga_valida
import time
import ui
import risultati
import impostazioni_ui
import diario_ui
import bobine_ui
import storico_ui
from consiglio import chiedi, orientamento_scelto, prompt_consiglio, prompt_diagnosi

st.set_page_config(page_title="STRATO · Assistente di stampa 3D", layout="wide", initial_sidebar_state="collapsed")
ui.imposta_stile()
for d in (config.LAVORI, config.FOTO):
    d.mkdir(exist_ok=True)

# campi del modulo "Il pezzo e cosa ti serve": salvati in richiesta.json e ripristinati alla riapertura
CAMPI_RICHIESTA = {"scopo": "scopo", "tipo": "uso", "priorita": "priorita", "condizioni": "ambiente",
                   "filamenti_disponibili": "filamenti", "multimateriale_per_supporti": "multimateriale",
                   "note": "note", "sollecitazione": "sollecitazione", "direzione_carico": "direzione_carico",
                   "parte_critica": "parte_critica", "profilo_filamento": "profilo_filamento",
                   "budget_ricerca": "budget_ricerca"}
CAMPI_RICHIESTA.update({k: k for k in ('usa_punti_carico', 'vincoli', 'zona_critica',
                                      'fissaggio_x', 'fissaggio_y', 'fissaggio_z', 'carico_x', 'carico_y', 'carico_z')})
FORMATI_MODELLO = {".stl", ".3mf", ".obj", ".step", ".stp"}
DEFAULT_RICHIESTA = {
    "scopo": "", "tipo": "funzionale / meccanico", "priorita": "robustezza e rigidità",
    "condizioni": [], "filamenti_disponibili": ["PLA", "PETG"], "multimateriale_per_supporti": False,
    "note": "", "sollecitazione": "non specificata", "direzione_carico": "non specificata",
    "parte_critica": "nessuna indicata", "profilo_filamento": config.PROFILO_FILAMENTO, "budget_ricerca": 4}
DEFAULT_RICHIESTA.update(usa_punti_carico=False, vincoli='', zona_critica='',
                        fissaggio_x=0., fissaggio_y=0., fissaggio_z=0., carico_x=0., carico_y=0., carico_z=10.)


@st.fragment(run_every='2s')
def mostra_avanzamento(cartella):
    stato = lavorazioni.stato(cartella)
    if stato.get('stato') != 'in corso':
        st.rerun()
    frazione = max(0., min(.99, stato.get('frazione', 0.)))
    fase = stato.get('fase', 'Avvio')
    completati, totale = stato.get('completati'), stato.get('totale')
    with st.container(key="analisi_avanzamento"):
        st.subheader(fase)
        passaggi_testo = f' — {completati} di {totale} completati' if totale is not None else ''
        st.progress(frazione, text=f'{int(frazione*100)}% — {fase}{passaggi_testo}')
        percentuale, passaggi = st.columns(2)
        percentuale.metric('Avanzamento', f'{int(frazione*100)}%')
        if completati is not None and totale is not None:
            passaggi.metric('Passaggi completati', f'{completati} di {totale}')
        trascorsi = max(0, int(time.time() - stato.get('inizio', time.time())))
        st.caption(f'Tempo trascorso: {trascorsi//60} min {trascorsi%60:02d} s. '
                   'Aggiornamento automatico ogni 2 secondi. La percentuale indica i passaggi, non il tempo residuo.')
        if 'frazione' not in stato:
            st.caption('Lavorazione avviata con la versione precedente: il dettaglio percentuale sarà disponibile dal prossimo avvio.')


def apri_lavoro(cartella, *, conserva_modello=False):
    """Apre un lavoro salvato: niente da ricalcolare, si rileggono i file della sua cartella.
    I campi del modulo si ripristinano al giro successivo, prima che i widget vengano creati."""
    if not conserva_modello:
        st.session_state.pop("modello_ui", None)
        st.session_state.pop("upload_ui", None)
    st.session_state["fase_ui"] = 6
    st.session_state["lavoro"] = str(cartella)
    st.query_params["lavoro"] = cartella.name     # nell'URL: il lavoro resta aperto anche ricaricando la pagina
    richiesta = cartella / "richiesta.json"
    if richiesta.exists():
        st.session_state["da_ripristinare"] = {
            **DEFAULT_RICHIESTA, **json.loads(richiesta.read_text(encoding="utf-8"))}
    else:
        st.session_state["da_ripristinare"] = DEFAULT_RICHIESTA.copy()


if "lavoro" not in st.session_state and "lavoro" in st.query_params:
    salvato = config.LAVORI / Path(st.query_params["lavoro"]).name
    if (salvato / "analisi.json").exists() or (salvato / "ingresso.json").exists():
        apri_lavoro(salvato)
for campo, chiave in CAMPI_RICHIESTA.items():
    if campo in st.session_state.get("da_ripristinare", {}):
        st.session_state[chiave] = st.session_state["da_ripristinare"][campo]
st.session_state.pop("da_ripristinare", None)

# I campi restano disponibili anche nelle fasi in cui i widget non sono montati.
for campo, chiave in CAMPI_RICHIESTA.items():
    st.session_state[chiave] = st.session_state.get(chiave, DEFAULT_RICHIESTA.get(campo))

# Conserva le preferenze anche quando i relativi widget non sono nella pagina corrente.
for chiave in ("provider_ai", "modello_codex", "modello_claude"):
    if chiave in st.session_state:
        st.session_state[chiave] = st.session_state[chiave]
provider, modello, SLICER, profilo_filamento, ADDON = impostazioni_ui.valori_attivi()


def tabella_confronto(dati, cartella):
    """Chi sceglie quale orientamento: nostra classifica, slicer (due modi), Claude."""
    per_id = {o["id"]: o for o in dati["orientamenti"]}
    scelte = [("Nostra classifica (primo posto)", dati["orientamenti"][0]["id"])]
    for s in dati.get("confronto_slicer", {}).get("scelte", []):
        scelte.append((s["chi"][0].upper() + s["chi"][1:], s["id"]))
    scelta_claude = cartella / "consiglio.json"
    if scelta_claude.exists():
        # la scelta è salvata come direzione: resta valida anche se la classifica cambia
        su = json.loads(scelta_claude.read_text(encoding="utf-8")).get("su")
        trovato = next((o["id"] for o in dati["orientamenti"] if su is not None
                        and orienta_slicer.direzione_su(o["trasformazione"]) @ su > 0.999), None)
        scelte.append((json.loads(scelta_claude.read_text(encoding="utf-8")).get("provider", "Claude"), trovato))
    elif (cartella / "consiglio.md").exists():
        scelte.append(("Claude", orientamento_scelto((cartella / "consiglio.md").read_text(encoding="utf-8"))))
    righe = []
    for chi, i in scelte:
        o = per_id.get(i, {})
        righe.append({"chi sceglie": chi, "orientamento": i if o else "n.d.", "origine": o.get("origine"),
                      "appoggio mm²": o.get("area_appoggio_mm2"),
                      "supporti dal piatto mm²": o.get("supporti_dal_piatto_area_mm2"),
                      "supporti sul pezzo mm²": o.get("supporti_sul_pezzo_area_mm2"),
                      "di cui in cavità mm²": o.get("supporti_in_cavita_area_mm2"),
                      "si ribalta": o.get("si_ribalta"), "brim": o.get("brim_consigliato"),
                      "supporti g (reali)": (o.get("slicer") or {}).get("supporti_g"),
                      "tempo (reale)": (o.get("slicer") or {}).get("tempo"),
                      "punteggio reale": o.get("punteggio_reale"),
                      "punteggio geometrico": classifica.punteggio_geometrico(o),
                      "costo slicer": o.get("costo_slicer")})
    return pd.DataFrame(righe)


def nome_lavoro(nome_file):
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(nome_file).stem)[:40]
    return f"{datetime.now():%Y%m%d-%H%M%S}_{base}"


def salva_analisi(cartella, dati):
    salva_json(cartella / "analisi.json", dati)


def immagini_lavoro(cartella, dati):
    """Griglia più viste dei primi due classificati; fallback per i lavori più vecchi."""
    immagini = [cartella / "orientamenti.png"]
    viste_primi = [cartella / f"viste_{o['id']}.png" for o in dati.get("orientamenti", [])[:2]]
    esistenti = [p for p in viste_primi if p.exists()]
    immagini += esistenti or sorted(cartella.glob("viste_*.png"))
    return [p for p in immagini if p.exists()]


def percorso_modello_lavoro(cartella, dati):
    """Trova la mesh anche se il progetto è stato spostato dopo aver salvato l'analisi."""
    salvato = Path(dati.get("file", ""))
    candidati = [salvato, cartella / salvato.name]
    candidati += sorted(p for p in cartella.iterdir() if p.suffix.lower() in {".stl", ".3mf", ".obj"})
    return next((p for p in candidati if p.is_file()), None)


def calcola_varianti(mesh, dati, cartella, filamento, priorita, avanzamento=None):
    """Compatibilità per gli strumenti locali; la dashboard usa il worker separato."""
    confronto.calcola(mesh, dati, cartella, {"priorita": priorita}, avanzamento)
    return dati["ottimizzazione_processo"]


def nome_file_sicuro(testo):
    """Nome leggibile e valido su Windows per i file scaricati dalla dashboard."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", testo).strip("._")


def stl_raccomandato(cartella, raccomandazione, varianti):
    """STL già ruotato e appoggiato sul piatto prodotto durante il sezionamento."""
    variante = next((v for v in varianti if v["id"] == raccomandazione["variante_id"]), None)
    if variante is None:
        return None
    orientamento = f"orientamento_{raccomandazione['orientamento_id']}"
    if variante.get("riferimento"):
        percorso = cartella / "sezionamenti" / orientamento / "pezzo.stl"
    else:
        percorso = cartella / "varianti" / orientamento / variante["id"] / "pezzo.stl"
    return percorso if percorso.is_file() else None


def impronta(contenuto):
    return hashlib.sha256(contenuto).hexdigest()


@st.cache_data(show_spinner=False)
def _impronta_file(percorso, _modificato):
    return impronta(Path(percorso).read_bytes())


@st.cache_data(show_spinner=False)
def _leggi_analisi(percorso, _modificato):
    dati = json.loads(Path(percorso).read_text(encoding="utf-8"))
    return classifica.applica(dati)


def lavori_salvati():
    """Le analisi complete (con analisi.json), dalla più recente. Per ognuna: cartella, analisi, impronte del file."""
    out = []
    for cartella in sorted((p for p in config.LAVORI.iterdir() if p.is_dir()), reverse=True):
        f = cartella / "analisi.json"
        if not f.exists():
            continue
        dati = _leggi_analisi(str(f), f.stat().st_mtime)
        # i lavori salvati prima dell'impronta in analisi.json: si calcola dal file nella cartella
        impronte = {dati["sha256"]} if "sha256" in dati else {
            _impronta_file(str(p), p.stat().st_mtime) for p in cartella.iterdir() if p.suffix.lower() in FORMATI_MODELLO}
        out.append({"cartella": cartella, "dati": dati, "impronte": impronte})
    return out


def descrivi_lavoro(cartella, dati):
    """'26/10 15:03 — sezionato con «Elegoo PETG @ECC» — consiglio di Claude'"""
    try:
        quando = datetime.strptime(cartella.name[:15], "%Y%m%d-%H%M%S").strftime("%d/%m/%Y %H:%M")
    except ValueError:
        quando = cartella.name
    parti = [quando]
    if "sezionamento" in dati:
        parti.append(f"sezionato con «{dati['sezionamento']['filamento']}»")
    parti.append("consiglio AI" if (cartella / "consiglio.md").exists() else "senza consiglio")
    return " — ".join(parti)




def mostra_controlli(cartella, dati, richiesta_corrente, sollecitazione):
    st.subheader("Geometria e verifiche")
    unione = dati.get('unione_solidi', {})
    if unione.get('applicata'):
        st.caption(f"Uniti {unione['corpi_originali']} solidi: volume, superficie e spessori descrivono il materiale risultante.")
    elif unione and not unione.get('misure_affidabili'):
        st.warning('La mesh non definisce un volume affidabile: spessori, volume e peso pieno non sono disponibili.')
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Dimensioni (mm)", " × ".join(f"{x:g}" for x in dati["dimensioni_mm"]))
    m2.metric("Volume", f"{dati['volume_cm3']} cm³" if dati["volume_cm3"] else "n.d.")
    sp = dati["spessori"]
    m3.metric("Spessore minimo", f"{sp.get('minimo_mm', '?')} mm", help=sp.get("nota"))
    m4.metric("Pareti sotto 1,2 mm", f"{sp.get('area_sotto_1_2mm_pct', '?')} %")
    if not dati["chiuso_stagno"]:
        st.info(f"Il modello non è perfettamente chiuso ({dati['bordi_aperti']} bordi aperti): "
                "di solito lo slicer lo ripara da solo, ma controlla l'anteprima.")
    def riga(o):
        r = {k: v for k, v in o.items() if k not in ("trasformazione", "slicer", "punteggio")}
        s = o.get("slicer") or {}
        if s and "errore" not in s:
            r.update({"filamento pezzo g": s["pezzo_g"], "filamento supporti g": s["supporti_g"],
                      "brim g": s["brim_g"], "tempo": s.get("tempo"), "tempo_s": s.get("tempo_s")})
        elif s:
            r["sezionamento"] = "errore: " + s["errore"]
        return r
    tabella = pd.DataFrame([riga(o) for o in dati["orientamenti"]])
    if "sezionamento" in dati:
        st.caption(f"Grammi e tempi: sezionamento reale con ElegooSlicer, filamento «{dati['sezionamento']['filamento']}». "
                   "I grammi sono il filamento estruso misurato nel G-code (lo slicer dichiara qualche decimo di grammo "
                   "in più per retrazioni e spurgo).")
    for col in ("avvisi", "scelto_da_slicer"):
        if col in tabella:
            tabella[col] = tabella[col].apply(lambda a: "; ".join(a) if isinstance(a, list) else a)
    st.dataframe(tabella.set_index("id"), width="stretch")
    if dati.get("classifica", {}).get("metodo") == "sezionamento_reale":
        st.caption("Classifica reale: grammi di supporto del G-code + stima delle sporgenze non servite dal profilo "
                   "solo dal piatto (peso triplo) + 25% del brim + penalità di stabilità. Più basso = meglio. "
                   "Il punteggio geometrico resta visibile per confronto.")
    else:
        st.caption("Classifica geometrica: più basso = meno supporti da togliere. I supporti che poggiano sul pezzo "
                   "pesano il triplo. Sarà sostituita dalla classifica reale quando ElegooSlicer è disponibile.")
    if "confronto_slicer" in dati:
        st.markdown("**Chi sceglie cosa**")
        st.dataframe(tabella_confronto(dati, cartella), width="stretch", hide_index=True)
        st.caption(dati["confronto_slicer"]["nota"])
    meccanica = confronto.meccanica(dati, richiesta_corrente)
    if meccanica:
        dati["analisi_meccanica"] = meccanica
        st.markdown("**Resistenza rispetto agli strati**")
        preferito = meccanica["orientamento_consigliato"]
        st.info(f"Per il carico dichiarato, l'orientamento {preferito} riduce maggiormente la componente "
                f"che tende a separare gli strati. Indicazione iniziale: {meccanica['pareti_consigliate']} pareti.")
        st.dataframe(pd.DataFrame(meccanica["risultati"])[[
            "orientamento_id", "carico_tra_strati_pct", "taglio_relativo_pct", "rischio_delaminazione"
        ]], width="stretch", hide_index=True)
        for avviso_meccanico in meccanica["avvisi"]:
            st.warning(avviso_meccanico)
        st.caption(meccanica["limite"])
        st.caption(meccanica['criterio'])
    elif sollecitazione != 'non specificata':
        st.warning('Caso meccanico non valutabile: verifica la direzione e che fissaggio e carico siano distinti. Gli urti non sono modellati.')
    else:
        dati.pop("analisi_meccanica", None)
    controlli_stampa = stampabilita.valuta(dati, config.VOLUME_STAMPA, config.UGELLO_MM)
    dati["stampabilita_avanzata"] = controlli_stampa
    st.markdown("**Controlli avanzati di stampabilità**")
    if controlli_stampa["controlli"]:
        tabella_controlli = pd.DataFrame([{
            "livello": r["gravita"].capitalize(), "controllo": r["controllo"],
            "orientamento": r.get('orientamento_id'),
            "problema": r["messaggio"], "cosa fare": r["azione"],
        } for r in controlli_stampa["controlli"]])
        st.dataframe(tabella_controlli, width="stretch", hide_index=True)
    else:
        st.success("Nessun problema rilevato dai controlli disponibili.")
    with st.expander("Limiti dei controlli automatici"):
        for limite_controllo in controlli_stampa["limiti"]:
            st.caption(limite_controllo)
    if st.button('Esegui i controlli dettagliati su sezioni e toolpath'):
        lavorazioni.avvia(cartella, 'controlli')
        st.rerun()
    dettaglio = dati.get('controlli_dettagliati')
    if dettaglio:
        st.caption(f"Ultimi controlli dettagliati: orientamento {dettaglio['orientamento_id']}, variante {dettaglio['variante']}.")
        with st.expander('Dettagli di cavità, ponti, fori e percorsi'):
            geometria = dettaglio.get('geometria') or {}
            percorso = dettaglio.get('toolpath') or {}
            st.caption(geometria.get('limite', geometria.get('motivo', '')))
            st.caption(percorso.get('limite', 'G-code non disponibile: controlli solo geometrici.'))
            for nome in ('cavita_chiuse', 'ponti', 'fori_piccoli', 'isole_geometriche'):
                if geometria.get(nome):
                    st.write(nome.replace('_', ' '))
                    st.dataframe(pd.DataFrame(geometria[nome]), hide_index=True)
            for nome in ('collisioni', 'isole_senza_appoggio', 'percorsi_disconnessi'):
                if percorso.get(nome):
                    st.write(nome.replace('_', ' '))
                    st.dataframe(pd.DataFrame(percorso[nome]), hide_index=True)
            if percorso.get('limitato') or percorso.get('archi_non_analizzati'):
                st.warning('Analisi del toolpath parziale: raggiunto il limite di segmenti o presenti archi non supportati.')
    profilo_usato = dati.get("sezionamento", {}).get("filamento", "")
    materiale_storico = calibrazione.materiale_da_profilo(profilo_usato, config.FILAMENTI)
    storico_personale = calibrazione.analizza(diario.tutte(), materiale_storico, profilo=profilo_usato) \
        if materiale_storico else calibrazione.analizza([])
    dati["calibrazione_personale"] = storico_personale
    if storico_personale["stampe_considerate"]:
        st.markdown("**Esperienza personale dal diario**")
        if storico_personale["problemi_ricorrenti"]:
            st.dataframe(pd.DataFrame(storico_personale["problemi_ricorrenti"]),
                         width="stretch", hide_index=True)
        elif not storico_personale["dati_sufficienti"]:
            st.caption(f"Una sola stampa annotata per {materiale_storico or 'questo materiale'}: "
                       "la registro, ma non la tratto ancora come una tendenza.")
        if storico_personale["compensazione_dimensionale"]:
            st.info(storico_personale["compensazione_dimensionale"]["indicazione"])
        st.caption(storico_personale["limite"])
        st.caption(storico_personale["origine_correzioni"])
    if dati.get("immagini_da_aggiornare"):
        st.warning("Le misure sono aggiornate; le immagini appartengono alla versione precedente dell'analisi.")
        if st.button("Aggiorna le immagini degli orientamenti"):
            lavorazioni.avvia(cartella, "immagini")
            st.rerun()
    if (cartella / "orientamenti.png").exists():
        st.image(str(cartella / "orientamenti.png"))
    for img in immagini_lavoro(cartella, dati)[1:]:
        st.image(str(img))

    if "augura" in dati:
        au = dati["augura"]
        st.markdown(f"**Controlli di augura** — geometria {au['geometria']}")
        gravita = {"error": "Errore", "warning": "Avviso", "info": "Info"}
        righe = [{"livello": gravita.get(f["severity"], f["severity"]), "controllo": f["kind"], "messaggio": f["message"]}
                 for f in au.get("controlli_come_nel_file", [])]
        if righe:
            st.dataframe(pd.DataFrame(righe), width="stretch", hide_index=True)
        if au.get("orientamenti"):
            st.caption("Orientamenti secondo augura (rotazione X, Y, Z in gradi rispetto al file)")
            st.dataframe(pd.DataFrame(au["orientamenti"]), width="stretch")
        for e in au.get("errori", []):
            st.warning(f"augura: {e}")




def mostra_download(cartella, dati, opt, esportazione):
    variante = next((v for v in opt.get("varianti", [])
                     if v["id"] == esportazione["variante_id"]), None)
    if variante:
        base = dati.get("sezionamento", {}).get("processo", config.PROFILO_PROCESSO)
        supporti = dati.get("sezionamento", {}).get("supporti", config.SUPPORTI_SEZIONAMENTO)
        pezzo = Path(dati.get("file", cartella.name)).stem
        nome_profilo = f"Assistente stampa - {pezzo} - {esportazione['variante']}"
        profilo = slicer_cli.profilo_utente(
            nome_profilo, base, variante["impostazioni"], supporti,
        )
        nome_base = nome_file_sicuro(f"{pezzo}_{esportazione['variante_id']}")
        c_3mf, c_stl, c_profilo = st.columns(3)
        c_profilo.download_button(
            "↓ Profilo JSON",
            json.dumps(profilo, ensure_ascii=False, indent=2),
            file_name=f"{nome_base}.json", width="stretch",
            mime="application/json",
            help='Scarica le impostazioni del processo selezionato: layer, pareti, riempimento e supporti. Non contiene il modello.',
        )
        orientato = stl_raccomandato(cartella, esportazione, opt.get("varianti", []))
        if orientato:
            c_stl.download_button(
                "↓ STL orientato",
                orientato.read_bytes(),
                file_name=f"{nome_file_sicuro(pezzo)}_orientamento_{esportazione['orientamento_id']}.stl", width="stretch",
                mime="model/stl",
                help='Contiene solo la geometria ruotata. Per lo stesso orientamento è uguale in tutte le varianti; non include impostazioni di stampa.',
            )
            nome_3mf = f"{nome_base}_orientamento_{esportazione['orientamento_id']}.3mf"
            progetto_3mf = cartella / "esportazioni" / nome_3mf
            modifiche = {**supporti, **variante["impostazioni"]}
            filamento_3mf = dati.get("sezionamento", {}).get("filamento", config.PROFILO_FILAMENTO)
            if slicer_cli.progetto_valido(orientato, progetto_3mf, base, filamento_3mf, modifiche):
                c_3mf.download_button(
                    "↓ Progetto 3MF", progetto_3mf.read_bytes(), width="stretch",
                    file_name=nome_3mf,
                    mime="application/vnd.ms-package.3dmanufacturing-3dmodel+xml",
                )
            elif c_3mf.button("Prepara progetto 3MF", type="primary", width="stretch",
                help='ElegooSlicer genera il progetto con modello orientato, processo selezionato, stampante e filamento. Al termine compare il download.'):
                salva_json(cartella / "esportazione.json", {
                    "stl": str(orientato.relative_to(cartella)),
                    "destinazione": str(progetto_3mf.relative_to(cartella)),
                    "processo": base, "filamento": filamento_3mf, "modifiche": modifiche})
                lavorazioni.avvia(cartella, "3mf")
                st.rerun()
        st.caption("3MF: modello e profilo · STL: geometria orientata · JSON: impostazioni.")



def mostra_bobina(dati, esportazione):
    materiale_g = esportazione.get("consumo_totale_g")
    filamento_scelto = dati.get("sezionamento", {}).get("filamento", "")
    materiale_bobina = calibrazione.materiale_da_profilo(filamento_scelto, config.FILAMENTI)
    if isinstance(materiale_g, (int, float)):
        disponibilita = bobine.stime(bobine.tutte(), materiale_bobina, materiale_g)
        if disponibilita:
            migliore_bobina = disponibilita[0]
            if migliore_bobina["sufficiente"]:
                costo = migliore_bobina["costo_stimato_eur"]
                costo_testo = f", costo stimato {costo:.2f} €" if costo is not None else ""
                st.info(f"Bobina «{migliore_bobina['bobina']}»: materiale sufficiente, "
                        f"restano circa {migliore_bobina['margine_g']:g} g con riserva del 5%{costo_testo}.")
            else:
                st.warning(f"Nessuna bobina {materiale_bobina or ''} registrata contiene i "
                           f"{materiale_g:g} g necessari.")
        else:
            st.caption("Verifica il materiale e registra una bobina pronta nella scheda Bobine.")
    else:
        st.caption("Consumo totale non disponibile: ricalcola i processi prima di verificare le bobine.")



def ricalcola_varianti(cartella, opt):
    varianti_calcolate = {v["id"]: v.get("impostazioni", {}) for v in opt.get("varianti", [])}
    varianti_mancanti = [v for v in config.VARIANTI_PROCESSO
                         if varianti_calcolate.get(v["id"]) != v["impostazioni"]]
    errori_varianti = any(not riga_valida(r) for r in opt.get("risultati", []))
    if SLICER:
        nomi_mancanti = ", ".join(v["nome"] for v in varianti_mancanti)
        etichetta = (f"Approfondisci con {nomi_mancanti}" if nomi_mancanti else
                     "Riprova i processi falliti" if errori_varianti else "Ricalcola e verifica i processi")
        if st.button(etichetta):
            lavorazioni.avvia(cartella, "varianti")
            st.rerun()
    st.caption("Tempo e materiale sono misurati; superficie e robustezza sono indicatori basati su layer, "
               "pareti e riempimento. Pareto indica le configurazioni non dominate sui quattro obiettivi.")




def mostra_consiglio(cartella, dati, richiesta_corrente):
    st.subheader(f"Il consiglio di {provider}")
    if st.button(f"Chiedi a {provider} come stamparlo", type="primary") or st.session_state.pop("richiedi_consiglio_ui", False):
        richiesta = richiesta_corrente
        immagini = [str(p) for p in immagini_lavoro(cartella, dati)]
        with st.spinner(f"{provider} sta guardando il pezzo..."):
            testo, costo, errore = chiedi(prompt_consiglio(dati, richiesta, immagini), cartella, modello,
                                         provider=provider, immagini=immagini)
        if errore or not testo:
            st.error(f"Qualcosa è andato storto: {errore or 'risposta vuota'}")
        else:
            salva_json(cartella / "richiesta.json", richiesta)
            (cartella / "consiglio.md").write_text(testo, encoding="utf-8")
            n = orientamento_scelto(testo)
            o = next((o for o in dati["orientamenti"] if o["id"] == n), None)
            (cartella / "consiglio.json").write_text(json.dumps({
                "scelta_id": n,
                "su": orienta_slicer.direzione_su(o["trasformazione"]).round(4).tolist() if o else None,
                "provider": provider, "modello": modello or "predefinito", "costo_usd": costo,
            }), encoding="utf-8")
    if (cartella / "consiglio.md").exists():
        st.markdown((cartella / "consiglio.md").read_text(encoding="utf-8"))
        info = json.loads((cartella / "consiglio.json").read_text(encoding="utf-8"))                 if (cartella / "consiglio.json").exists() else {}
        st.caption(f"Consiglio salvato di {info.get('provider', 'Claude')} · Modello {info.get('modello', 'non registrato')}")
        if info.get("costo_usd") is not None:
            st.caption(f"Modello {info.get('modello')}, equivalente API: {info['costo_usd']:.3f} $")
        st.info("Dopo la stampa annota com'è andata nella scheda **Diario di stampa**: "
                "le prossime analisi ne terranno conto.")



# ------------------------------------------------------------------ analisi
def mostra_analisi():
    if "lavoro" in st.session_state:
        st.query_params["lavoro"] = Path(st.session_state["lavoro"]).name
    fase = st.session_state.setdefault("fase_ui", 6 if "lavoro" in st.session_state else 1)
    cartella_lavoro = Path(st.session_state["lavoro"]) if "lavoro" in st.session_state else None
    stato_lavoro = lavorazioni.stato(cartella_lavoro) if cartella_lavoro else {}
    lavorazione_attiva = stato_lavoro.get("stato") == "in corso"
    if lavorazione_attiva:
        fase = 5
    file = st.session_state.get("modello_ui")
    file_contesto = file if fase < 5 else None
    if file_contesto is None and cartella_lavoro and fase >= 5:
        ingresso = cartella_lavoro / "ingresso.json"
        if ingresso.exists():
            nome_modello = json.loads(ingresso.read_text(encoding="utf-8")).get("file", "")
            modello_salvato = cartella_lavoro / Path(nome_modello).name
        else:
            modello_salvato = next((p for p in cartella_lavoro.iterdir()
                                    if p.suffix.lower() in FORMATI_MODELLO), None)
        if modello_salvato and modello_salvato.is_file():
            file_contesto = modello_salvato
    if fase == 1:
        stato_header = ("FILE SELEZIONATO", file.name) if file else (
            "NESSUN FILE SELEZIONATO", "Carica un modello per continuare")
    elif fase == 5:
        stato_header = "La percentuale indica i passaggi completati, non il tempo residuo."
    elif fase == 6:
        stato_header = ("LAVORAZIONE INTERROTTA" if stato_lavoro.get("stato") in ("errore", "interrotta")
                        else "RISULTATO SALVATO", file_contesto.name if file_contesto else "")
    elif fase == 4:
        stato_header = "Geometria e slicer lavorano in locale. Il consiglio AI resta facoltativo."
    else:
        stato_header = "Le scelte restano salvate durante il percorso."
    indietro, alternativa, avanti = ui.barra_intestazione("analisi", stato=stato_header)
    if fase <= 4:
        if fase > 1:
            indietro.button("← Indietro", on_click=ui.vai_fase,
                            args=(fase - 1,), key="percorso_indietro", width="stretch")
        if fase < 4:
            etichetta_avanti = {1: "Continua a Utilizzo →", 2: "Continua a Priorità →",
                               3: "Vai al riepilogo →"}[fase]
            avanti.button(etichetta_avanti, type="primary", disabled=not file,
                          on_click=ui.vai_fase, args=(fase + 1,),
                          key="percorso_avanti", width="stretch")
    with st.container(key="upload_path"):
        ui.percorso(fase, "lavoro" in st.session_state)
    if fase == 1:
        ui.titolo_caricamento(config.STAMPANTE)
    else:
        ui.titolo_fase(fase)
    priorita = st.session_state["priorita"]
    sollecitazione = st.session_state["sollecitazione"]
    if fase == 1:
        with st.container(key="upload_layout"):
            colonna_modello, parametri = st.columns([926, 450])
            with colonna_modello:
                ui.selezione_modello(file, ADDON)
                st.html('<aside class="upload-local">Geometria e slicer lavorano in locale. '
                        'Claude o Codex intervengono solo su richiesta.</aside>')
            with parametri:
                ui.piatto_caricamento(config.STAMPANTE, config.VOLUME_STAMPA)
    elif fase <= 4:
        with st.container(key="wizard_layout"):
            principale, contesto = st.columns([926, 450], gap="large")
            with principale, st.container(key="wizard_main"):
                if fase == 2:
                    st.subheader("Utilizzo del pezzo")
                    # valori iniziali in session_state e non come default dei widget: così la riapertura può sovrascriverli
                    st.session_state.setdefault("filamenti", ["PLA", "PETG"])
                    scopo = st.text_area("A cosa serve, dove va montato", key="scopo",
                                         placeholder="es. pulsante della lavatrice: la linguetta fa da molla, il perno preme l'interruttore")
                    c1, c2 = st.columns(2)
                    with c1:
                        uso = st.selectbox("Tipo di pezzo", ["funzionale / meccanico", "estetico", "prototipo veloce", "misto"], key="uso")
                    with c2:
                        ambiente = st.multiselect("Condizioni d'uso", ["caldo oltre 50 °C", "umidità o acqua", "all'aperto (sole)",
                                                                       "sforzi ripetuti / flessione", "urti", "contatto con alimenti"],
                                                  key="ambiente", placeholder="Seleziona le condizioni d’uso…")
                    c3, c4 = st.columns(2)
                    with c3:
                        filamenti = st.multiselect("Filamenti che hai", config.FILAMENTI, key="filamenti",
                                                   placeholder="Seleziona i filamenti disponibili…")
                    with c4:
                        note = st.text_input("Altro (lato da tenere bello, problemi avuti, ecc.)", key="note")
                    multimateriale = st.checkbox("Ho un sistema multimateriale (es. CANVAS) per l'interfaccia dei supporti",
                                                 key="multimateriale")

                    with st.expander("Carichi e resistenza degli strati"):
                        m1, m2, m3 = st.columns(3)
                        sollecitazione = m1.selectbox(
                            "Sollecitazione principale",
                            ["non specificata", "trazione", "compressione", "flessione", "torsione", "urti ripetuti"],
                            key="sollecitazione",
                        )
                        direzione_carico = m2.selectbox(
                            "Direzione rispetto al file",
                            ["non specificata", *resistenza.DIREZIONI],
                            key="direzione_carico",
                        )
                        parte_critica = m3.selectbox(
                            "Parte più critica",
                            ["nessuna indicata", "perno", "linguetta flessibile", "gancio", "foro/fissaggio", "parete sottile"],
                            key="parte_critica",
                        )
                        st.text_input('Fissaggi e vincoli', key='vincoli', placeholder='es. incastro alla base, due viti')
                        st.text_input('Zona critica caricata', key='zona_critica', placeholder='es. radice del gancio, parete laterale')
                        usa_punti = st.checkbox('Indico fissaggio e applicazione del carico nel file (mm)', key='usa_punti_carico')
                        if usa_punti:
                            for prefisso, etichetta in (('fissaggio', 'Fissaggio'), ('carico', 'Applicazione carico')):
                                colonne = st.columns(3)
                                for colonna, asse in zip(colonne, 'xyz'):
                                    st.session_state.setdefault(prefisso + '_' + asse, DEFAULT_RICHIESTA[prefisso + '_' + asse])
                                    colonna.number_input(f'{etichetta} {asse.upper()} mm', key=prefisso + '_' + asse)
                        st.caption('La direzione selezionata è quella della forza; in torsione rappresenta l’asse se non specifichi i punti. '
                                   'Punti distinti definiscono l’asse fissaggio–carico per flessione/torsione. Il confronto usa tensioni ideali, non una FEM. '
                                   'Gli urti richiedono una verifica separata.')
                if fase == 3:
                    st.subheader("Scegli la priorità")
                    descrizioni_priorita = {
                        "robustezza e rigidità": "Privilegia orientamento e processo per un pezzo funzionale.",
                        "superficie bella": "Dai più peso alla finitura delle superfici visibili.",
                        "precisione delle misure": "Concentrati sui dettagli e sulle quote del modello.",
                        "velocità di stampa": "Riduci il tempo stimato dallo slicer.",
                        "poco materiale": "Riduci il consumo totale di filamento.",
                    }
                    with st.container(key="priorita_scelte"):
                        priorita = st.radio("Cosa conta di più", list(descrizioni_priorita), key="priorita",
                                            format_func=lambda valore: f"**{valore[0].upper() + valore[1:]}**  \n{descrizioni_priorita[valore]}",
                                            label_visibility="collapsed", width="stretch")
                    with st.container(key="ricerca_parametri"):
                        st.markdown("**Ricerca dei parametri**")
                        st.session_state.setdefault('budget_ricerca', 4)
                        st.number_input('Prove aggiuntive oltre i preset', min_value=0, max_value=8, key='budget_ricerca')
                        st.caption('La ricerca modifica un parametro alla volta attorno alle configurazioni migliori. '
                                   'Il compromesso pesa tempo, materiale, layer e robustezza attesa al 25% ciascuno.')

                if fase == 4:
                    st.subheader("Il punto di partenza")
                    with st.container(key="riepilogo"):
                        for etichetta, valore in (
                            ("Modello", file.name if file else "Nessun modello selezionato"),
                            ("Utilizzo", st.session_state["scopo"] or "Non specificato"),
                            ("Tipo", st.session_state["uso"]),
                            ("Materiali", ", ".join(st.session_state["filamenti"])),
                            ("Priorità", priorita),
                            ("Ricerca", f"{st.session_state['budget_ricerca']} prove aggiuntive"),
                            ("Stampante", config.STAMPANTE["modello"]),
                            ("Profilo filamento", profilo_filamento if SLICER else "Slicer non disponibile"),
                        ):
                            st.html(f'<div class="summary-row"><span>{escape(etichetta)}</span>'
                                    f'<span>{escape(str(valore))}</span></div>')
            with contesto:
                ui.contesto_pezzo(file_contesto, config.STAMPANTE, st.session_state["filamenti"], fase=fase)

    analizza_ora = False
    if file and fase == 4:
        sha = impronta(file.getvalue())
        gia_fatto = next((l for l in lavori_salvati() if sha in l["impronte"]), None)
        if gia_fatto is None:
            analizza_ora = avanti.button("Avvia analisi →", type="primary", width="stretch")
        elif str(gia_fatto["cartella"]) == st.session_state.get("lavoro"):
            st.caption(f"Stai guardando l'analisi salvata di questo file ({descrivi_lavoro(gia_fatto['cartella'], gia_fatto['dati'])}).")
            analizza_ora = avanti.button("Rifai l'analisi da capo", width="stretch")
        else:
            st.info(f"Questo file è già stato analizzato: {descrivi_lavoro(gia_fatto['cartella'], gia_fatto['dati'])}. "
                    "Puoi riaprire l'analisi salvata senza rifare i calcoli.")
            if alternativa.button("Riapri l'analisi salvata", type="primary"):
                apri_lavoro(gia_fatto["cartella"])
                st.rerun()
            analizza_ora = avanti.button("Rifai l'analisi da capo", width="stretch")

    richiesta_corrente = {campo: st.session_state.get(chiave, DEFAULT_RICHIESTA.get(campo))
                         for campo, chiave in CAMPI_RICHIESTA.items()}
    richiesta_corrente["profilo_filamento"] = profilo_filamento if SLICER else config.PROFILO_FILAMENTO
    if "lavoro" in st.session_state:
        salva_json(Path(st.session_state["lavoro"]) / "richiesta.json", richiesta_corrente)

    if analizza_ora:
        cartella = config.LAVORI / nome_lavoro(file.name)
        cartella.mkdir(parents=True)
        originale = cartella / Path(file.name).name
        originale.write_bytes(file.getvalue())
        salva_json(cartella / "ingresso.json", {"file": originale.name, "sha256": sha})
        salva_json(cartella / "richiesta.json", richiesta_corrente)
        apri_lavoro(cartella, conserva_modello=True)
        lavorazioni.avvia(cartella)
        st.rerun()

    if fase >= 5:
        if lavorazione_attiva or stato_lavoro.get("stato") in ("errore", "interrotta"):
            with st.container(key="wizard_layout"):
                principale, contesto = st.columns([926, 450], gap="large")
                with principale, st.container(key="wizard_main"):
                    st.subheader("Analisi in corso" if lavorazione_attiva else "Lavorazione interrotta")
                    if lavorazione_attiva:
                        mostra_avanzamento(cartella_lavoro)
                        if avanti.button("Aggiorna avanzamento"):
                            st.rerun()
                    else:
                        st.warning(stato_lavoro.get("errore", "Lavorazione interrotta"))
                        if avanti.button("Riprendi la lavorazione"):
                            lavorazioni.avvia(cartella_lavoro, stato_lavoro.get("modo", "completa"))
                            st.rerun()
                with contesto:
                    ui.contesto_pezzo(file_contesto, config.STAMPANTE, st.session_state["filamenti"], fase=5)

        if ("lavoro" in st.session_state and not lavorazione_attiva
                and (Path(st.session_state["lavoro"]) / "analisi.json").exists()):
            cartella = Path(st.session_state["lavoro"])
            dati = json.loads((cartella / "analisi.json").read_text(encoding="utf-8"))
            if dati.get("versione_geometria", 1) < config.VERSIONE_GEOMETRIA:
                percorso_mesh = percorso_modello_lavoro(cartella, dati)
                if percorso_mesh is not None:
                    if alternativa.button("Aggiorna la geometria salvata"):
                        lavorazioni.avvia(cartella, "geometria")
                        st.rerun()
                    st.warning("Geometria salvata con una versione precedente: aggiornala prima del confronto.")
                else:
                    st.warning(
                        "Non posso aggiornare la geometria perché il file del modello non è più disponibile."
                    )
            dati = classifica.applica(dati)
            with st.container(key="risultati"):
                risultati.mostra(
                    cartella, dati, richiesta_corrente, SLICER,
                    percorso_modello_lavoro(cartella, dati),
                    download=lambda opt, scelta: mostra_download(cartella, dati, opt, scelta),
                    bobina=lambda scelta: mostra_bobina(dati, scelta),
                    controlli=lambda: mostra_controlli(cartella, dati, richiesta_corrente, sollecitazione),
                    consiglio=lambda: mostra_consiglio(cartella, dati, richiesta_corrente),
                    ricalcola=lambda opt: ricalcola_varianti(cartella, opt),
                    header_avanti=avanti,
                )


def mostra_diario():
    diario_ui.mostra(provider, modello)


def apri_da_storico(cartella):
    apri_lavoro(cartella)
    st.switch_page(pagina_analisi, query_params={"lavoro": cartella.name})


def nuovo_da_storico():
    risultati.nuovo_pezzo()
    st.switch_page(pagina_analisi)


def mostra_storico():
    storico_ui.mostra(lavori_salvati, descrivi_lavoro, apri_da_storico, nuovo_da_storico)


pagina_analisi = st.Page(mostra_analisi, title="Analisi", default=True)
pagine = [pagina_analisi,
          st.Page(mostra_diario, title="Diario", url_path="diario"),
          st.Page(bobine_ui.mostra, title="Bobine", url_path="bobine"),
          st.Page(mostra_storico, title="Storico", url_path="storico"),
          st.Page(impostazioni_ui.mostra, title="Impostazioni", url_path="impostazioni")]
pagina = st.navigation(pagine, position="hidden")
with st.container(key="navigazione", horizontal=True):
    for voce in pagine:
        parametri = ({"lavoro": Path(st.session_state["lavoro"]).name}
                     if voce is pagina_analisi and "lavoro" in st.session_state else None)
        with st.container(key="nav_attiva" if voce is pagina else f"nav_{voce.title.lower()}"):
            st.page_link(voce, label=voce.title, width="stretch", query_params=parametri)
pagina.run()
