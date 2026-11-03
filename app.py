"""Assistente di stampa 3D. Avvio:  streamlit run app.py

analisi e render (trimesh, matplotlib) si importano solo quando si analizza un pezzo:
caricarli all'avvio costava più di dieci secondi prima che comparisse la pagina."""
import hashlib
import json
import re
from datetime import datetime
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
from consiglio import chiedi, orientamento_scelto, prompt_consiglio, prompt_diagnosi

st.set_page_config(page_title="Assistente stampa 3D", page_icon="🧩", layout="wide")
for d in (config.LAVORI, config.FOTO):
    d.mkdir(exist_ok=True)

# campi del modulo "Il pezzo e cosa ti serve": salvati in richiesta.json e ripristinati alla riapertura
CAMPI_RICHIESTA = {"scopo": "scopo", "tipo": "uso", "priorita": "priorita", "condizioni": "ambiente",
                   "filamenti_disponibili": "filamenti", "multimateriale_per_supporti": "multimateriale",
                   "note": "note", "sollecitazione": "sollecitazione", "direzione_carico": "direzione_carico",
                   "parte_critica": "parte_critica"}
FORMATI_MODELLO = {".stl", ".3mf", ".obj", ".step", ".stp"}


def apri_lavoro(cartella):
    """Apre un lavoro salvato: niente da ricalcolare, si rileggono i file della sua cartella.
    I campi del modulo si ripristinano al giro successivo, prima che i widget vengano creati."""
    st.session_state["lavoro"] = str(cartella)
    st.query_params["lavoro"] = cartella.name     # nell'URL: il lavoro resta aperto anche ricaricando la pagina
    richiesta = cartella / "richiesta.json"
    if richiesta.exists():
        st.session_state["da_ripristinare"] = json.loads(richiesta.read_text(encoding="utf-8"))


if "lavoro" not in st.session_state and "lavoro" in st.query_params:
    salvato = config.LAVORI / Path(st.query_params["lavoro"]).name
    if (salvato / "analisi.json").exists():
        apri_lavoro(salvato)
for campo, chiave in CAMPI_RICHIESTA.items():
    if campo in st.session_state.get("da_ripristinare", {}):
        st.session_state[chiave] = st.session_state["da_ripristinare"][campo]
st.session_state.pop("da_ripristinare", None)

with st.sidebar:
    st.header("Impostazioni")
    modello = config.MODELLI[st.selectbox("Modello di Claude", list(config.MODELLI))]
    st.caption("Usa il login di Claude Code di questo PC: con l'abbonamento non c'è costo extra, "
               "conta sui limiti d'uso. Il costo mostrato è l'equivalente API.")
    st.subheader("Stampante")
    st.json(config.STAMPANTE, expanded=False)
    st.subheader("Sezionamento reale")
    SLICER = slicer_cli.disponibile()
    if SLICER:
        filamenti_slicer = slicer_cli.filamenti_disponibili()
        profilo_filamento = st.selectbox("Profilo filamento", filamenti_slicer,
                                         index=filamenti_slicer.index(config.PROFILO_FILAMENTO)
                                         if config.PROFILO_FILAMENTO in filamenti_slicer else 0)
        st.caption(f"ElegooSlicer seziona ogni orientamento con «{config.PROFILO_PROCESSO}» e supporti ad albero "
                   f"solo dal piatto (soglia {config.SOGLIA_SUPPORTI}°): grammi e tempi veri, non stime.")
    else:
        st.caption("ElegooSlicer non trovato: niente sezionamento reale.")
    st.subheader("Add-on")
    ADDON = augura_addon.disponibile()
    if ADDON:
        st.success("augura attivo: file STEP e controlli esatti (solo sugli STEP)")
        with st.popover("Rimuovi augura"):
            st.caption("Cancella l'ambiente `.venv-augura` (circa 700 MB). Si potrà reinstallare da qui.")
            if st.button("Conferma la rimozione", type="primary"):
                try:
                    augura_addon.rimuovi()
                except OSError as e:
                    st.error(f"Rimozione non riuscita: {e}")
                else:
                    st.rerun()
    else:
        st.caption("augura non installato (facoltativo). Aggiunge i file STEP e controlli esatti su di essi.")
        if st.button(f"Scarica e installa augura {augura_addon.VERSIONE} (circa 700 MB)"):
            with st.status("Installazione di augura: può volerci qualche minuto...", expanded=True) as stato:
                registro = st.empty()
                righe = []
                try:
                    for riga in augura_addon.installa():
                        righe = (righe + [riga])[-15:]
                        registro.code("\n".join(righe), language=None)
                except Exception as e:
                    stato.update(label=f"Installazione non riuscita: {e}", state="error")
                else:
                    stato.update(label="augura installato", state="complete")
                    st.rerun()

tab_analisi, tab_diario, tab_bobine, tab_storico = st.tabs(
    ["Analizza un pezzo", "Diario di stampa", "Bobine", "Analisi passate"]
)


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
        scelte.append(("Claude", trovato))
    elif (cartella / "consiglio.md").exists():
        scelte.append(("Claude", orientamento_scelto((cartella / "consiglio.md").read_text(encoding="utf-8"))))
    righe = []
    for chi, i in scelte:
        o = per_id.get(i, {})
        righe.append({"chi sceglie": chi, "orientamento": i if o else "n.d.", "origine": o.get("origine"),
                      "appoggio mm²": o.get("area_appoggio_mm2"),
                      "supporti dal piatto mm²": o.get("supporti_dal_piatto_area_mm2"),
                      "supporti sul pezzo mm²": o.get("supporti_sul_pezzo_area_mm2"),
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
    (cartella / "analisi.json").write_text(json.dumps(dati, ensure_ascii=False, indent=2), encoding="utf-8")


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
    """Seziona Dettaglio e Veloce sui primi orientamenti; Bilanciato riusa i dati esistenti."""
    selezionati = dati["orientamenti"][:config.NUM_ORIENTAMENTI_VARIANTI]
    extra = slicer_cli.seziona_varianti(
        mesh, selezionati, cartella / "varianti", config.PROFILO_PROCESSO, filamento,
        config.VARIANTI_PROCESSO, avanzamento,
    )
    dati["ottimizzazione_processo"] = ottimizzazione.costruisci(
        dati["orientamenti"], config.VARIANTI_PROCESSO, extra, priorita,
        config.NUM_ORIENTAMENTI_VARIANTI,
    )
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
    parti.append("consiglio di Claude" if (cartella / "consiglio.md").exists() else "senza consiglio")
    return " — ".join(parti)


# ------------------------------------------------------------------ analisi
with tab_analisi:
    st.subheader("1. Il pezzo e cosa ti serve")
    formati = ["stl", "3mf", "obj"] + (["step", "stp"] if ADDON else [])
    file = st.file_uploader("File da stampare", type=formati)
    c1, c2 = st.columns(2)
    # valori iniziali in session_state e non come default dei widget: così la riapertura può sovrascriverli
    st.session_state.setdefault("filamenti", ["PLA", "PETG"])
    with c1:
        scopo = st.text_area("A cosa serve, dove va montato", key="scopo",
                             placeholder="es. pulsante della lavatrice: la linguetta fa da molla, il perno preme l'interruttore")
        uso = st.selectbox("Tipo di pezzo", ["funzionale / meccanico", "estetico", "prototipo veloce", "misto"], key="uso")
        priorita = st.selectbox("Cosa conta di più", ["robustezza e rigidità", "superficie bella", "precisione delle misure",
                                                      "velocità di stampa", "poco materiale"], key="priorita")
    with c2:
        ambiente = st.multiselect("Condizioni d'uso", ["caldo oltre 50 °C", "umidità o acqua", "all'aperto (sole)",
                                                       "sforzi ripetuti / flessione", "urti", "contatto con alimenti"],
                                  key="ambiente")
        filamenti = st.multiselect("Filamenti che hai", config.FILAMENTI, key="filamenti")
        multimateriale = st.checkbox("Ho un sistema multimateriale (es. CANVAS) per l'interfaccia dei supporti",
                                     key="multimateriale")
        note = st.text_input("Altro (lato da tenere bello, problemi avuti, ecc.)", key="note")

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
        st.caption("Serve a confrontare la direzione degli strati; non sostituisce una simulazione strutturale.")

    analizza_ora = False
    if file:
        sha = impronta(file.getvalue())
        gia_fatto = next((l for l in lavori_salvati() if sha in l["impronte"]), None)
        if gia_fatto is None:
            analizza_ora = st.button("Analizza la geometria", type="primary")
        elif str(gia_fatto["cartella"]) == st.session_state.get("lavoro"):
            st.caption(f"Stai guardando l'analisi salvata di questo file ({descrivi_lavoro(gia_fatto['cartella'], gia_fatto['dati'])}).")
            analizza_ora = st.button("Rifai l'analisi da capo")
        else:
            st.info(f"Questo file è già stato analizzato: {descrivi_lavoro(gia_fatto['cartella'], gia_fatto['dati'])}. "
                    "Puoi riaprire l'analisi salvata senza rifare i calcoli.")
            b1, b2 = st.columns([1, 3])
            if b1.button("Riapri l'analisi salvata", type="primary"):
                apri_lavoro(gia_fatto["cartella"])
                st.rerun()
            analizza_ora = b2.button("Rifai l'analisi da capo")

    if analizza_ora:
        from analisi import analizza
        from render import griglia_orientamenti, viste
        cartella = config.LAVORI / nome_lavoro(file.name)
        cartella.mkdir(parents=True)
        originale = cartella / file.name
        originale.write_bytes(file.getvalue())
        percorso = originale
        if originale.suffix.lower() in augura_addon.FORMATI_STEP:
            percorso = originale.with_suffix(".stl")
            with st.spinner("Converto lo STEP in STL..."):
                augura_addon.step_in_stl(originale, percorso)
        with st.spinner("Calcolo spessori, sporgenze e orientamenti..."):
            mesh, dati = analizza(percorso)
            dati["sha256"] = sha
            griglia_orientamenti(mesh, dati["orientamenti"], cartella / "orientamenti.png")
            for o in dati["orientamenti"][:2]:
                viste(mesh, o["trasformazione"], cartella / f"viste_{o['id']}.png",
                      f"Orientamento {o['id']} ({o['origine']})")
        # salvata subito: se il sezionamento viene interrotto, l'analisi geometrica resta
        salva_analisi(cartella, dati)
        apri_lavoro(cartella)
        if SLICER:
            # ogni interazione con la pagina fa ripartire lo script e butta via il lavoro in corso
            avviso = st.info("Seziono gli orientamenti e poi confronto tre processi sui migliori: "
                             "non toccare la pagina finché non finisce.")
            n = len(dati["orientamenti"])
            extra_totali = min(n, config.NUM_ORIENTAMENTI_VARIANTI) * sum(
                not v.get("riferimento") for v in config.VARIANTI_PROCESSO)
            totale_sezionamenti = n + extra_totali
            barra = st.progress(0.0, text=f"ElegooSlicer seziona {n} orientamenti...")

            def avanzamento(i, o):
                barra.progress(i / totale_sezionamenti,
                               text=f"ElegooSlicer seziona l'orientamento {o['id']} ({i + 1} di {n})...")

            slicer_cli.seziona_orientamenti(mesh, dati["orientamenti"], cartella / "sezionamenti",
                                            config.PROFILO_PROCESSO, profilo_filamento,
                                            config.SUPPORTI_SEZIONAMENTO, avanzamento)
            classifica.applica(dati)

            def avanzamento_variante(i, o, variante, totale):
                barra.progress((n + i) / (n + extra_totali),
                               text=f"Confronto processi: orientamento {o['id']}, {variante['nome']} "
                                    f"({i + 1} di {totale})...")

            calcola_varianti(mesh, dati, cartella, profilo_filamento, priorita, avanzamento_variante)
            barra.progress(1.0, text="Confronto dei processi completato")
            # Il vincitore reale può essere diverso da quello geometrico: riallinea
            # griglia e viste dettagliate senza cambiare gli ID degli orientamenti.
            griglia_orientamenti(mesh, dati["orientamenti"], cartella / "orientamenti.png")
            for o in dati["orientamenti"][:2]:
                viste(mesh, o["trasformazione"], cartella / f"viste_{o['id']}.png",
                      f"Orientamento {o['id']} ({o['origine']})")
            barra.empty()
            avviso.empty()
            dati["sezionamento"] = {"processo": config.PROFILO_PROCESSO, "filamento": profilo_filamento,
                                    "supporti": config.SUPPORTI_SEZIONAMENTO}
        # sugli STL augura ripete in modo approssimato controlli che l'analisi fa già: solo per gli STEP
        if ADDON and originale.suffix.lower() in augura_addon.FORMATI_STEP:
            with st.spinner("Controlli di augura sulla geometria esatta dello STEP..."):
                dati["augura"] = augura_addon.verifica(originale)
        salva_analisi(cartella, dati)

    if "lavoro" in st.session_state and not (Path(st.session_state["lavoro"]) / "analisi.json").exists():
        st.warning("Questa analisi era stata interrotta prima di essere salvata: ricarica il file e rifalla.")
        del st.session_state["lavoro"]
        st.query_params.pop("lavoro", None)

    if "lavoro" in st.session_state:
        cartella = Path(st.session_state["lavoro"])
        dati = classifica.applica(json.loads((cartella / "analisi.json").read_text(encoding="utf-8")))
        st.subheader("2. Cosa dice la geometria")
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
        meccanica = resistenza.valuta(
            dati["orientamenti"], direzione_carico, sollecitazione, parte_critica, dati.get("spessori"),
        )
        if meccanica:
            dati["analisi_meccanica"] = meccanica
            st.markdown("**Resistenza rispetto agli strati**")
            preferito = meccanica["orientamento_consigliato"]
            st.info(f"Per il carico dichiarato, l'orientamento {preferito} riduce maggiormente la componente "
                    f"che tende a separare gli strati. Indicazione iniziale: {meccanica['pareti_consigliate']} pareti.")
            st.dataframe(pd.DataFrame(meccanica["risultati"])[[
                "orientamento_id", "carico_tra_strati_pct", "rischio_delaminazione"
            ]], width="stretch", hide_index=True)
            for avviso_meccanico in meccanica["avvisi"]:
                st.warning(avviso_meccanico)
            st.caption(meccanica["limite"])
        else:
            dati.pop("analisi_meccanica", None)
        controlli_stampa = stampabilita.valuta(dati, config.VOLUME_STAMPA, config.UGELLO_MM)
        dati["stampabilita_avanzata"] = controlli_stampa
        st.markdown("**Controlli avanzati di stampabilità**")
        if controlli_stampa["controlli"]:
            icone = {"errore": "🔴", "avviso": "🟠", "info": "🔵"}
            tabella_controlli = pd.DataFrame([{
                "livello": icone[r["gravita"]], "controllo": r["controllo"],
                "problema": r["messaggio"], "cosa fare": r["azione"],
            } for r in controlli_stampa["controlli"]])
            st.dataframe(tabella_controlli, width="stretch", hide_index=True)
        else:
            st.success("Nessun problema rilevato dai controlli disponibili.")
        with st.expander("Limiti dei controlli automatici"):
            for limite_controllo in controlli_stampa["limiti"]:
                st.caption(limite_controllo)
        profilo_usato = dati.get("sezionamento", {}).get("filamento", "")
        materiale_storico = calibrazione.materiale_da_profilo(profilo_usato, config.FILAMENTI)
        storico_personale = calibrazione.analizza(diario.tutte(), materiale_storico)
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
        st.image(str(cartella / "orientamenti.png"))
        for img in immagini_lavoro(cartella, dati)[1:]:
            st.image(str(img))

        if "augura" in dati:
            au = dati["augura"]
            st.markdown(f"**Controlli di augura** — geometria {au['geometria']}")
            gravita = {"error": "🔴 errore", "warning": "🟠 avviso", "info": "🔵 info"}
            righe = [{"livello": gravita.get(f["severity"], f["severity"]), "controllo": f["kind"], "messaggio": f["message"]}
                     for f in au.get("controlli_come_nel_file", [])]
            if righe:
                st.dataframe(pd.DataFrame(righe), width="stretch", hide_index=True)
            if au.get("orientamenti"):
                st.caption("Orientamenti secondo augura (rotazione X, Y, Z in gradi rispetto al file)")
                st.dataframe(pd.DataFrame(au["orientamenti"]), width="stretch")
            for e in au.get("errori", []):
                st.warning(f"augura: {e}")

        st.subheader("3. Confronto delle varianti di processo")
        if "ottimizzazione_processo" not in dati and SLICER and "sezionamento" in dati:
            st.caption("Questa analisi è precedente al confronto automatico. Puoi calcolarlo senza rifare la geometria "
                       "né i sezionamenti già presenti.")
            if st.button("Confronta Dettaglio, Bilanciato e Veloce"):
                from analisi import carica
                percorso_mesh = percorso_modello_lavoro(cartella, dati)
                if percorso_mesh is None:
                    st.error("Il file del modello salvato non è più disponibile: occorre rifare l'analisi.")
                else:
                    mesh = carica(percorso_mesh)
                    barra_varianti = st.progress(0.0, text="Preparo il confronto dei processi...")

                    def avanzamento_storico(i, o, variante, totale):
                        barra_varianti.progress(i / totale, text=f"Orientamento {o['id']}, {variante['nome']} "
                                                          f"({i + 1} di {totale})...")

                    filamento_usato = dati["sezionamento"]["filamento"]
                    calcola_varianti(mesh, dati, cartella, filamento_usato, priorita, avanzamento_storico)
                    salva_analisi(cartella, dati)
                    st.rerun()

        if "ottimizzazione_processo" in dati:
            opt = ottimizzazione.aggiorna_priorita(dati["ottimizzazione_processo"], priorita)
            rac = opt.get("raccomandazione")
            if rac:
                st.success(f"Per «{priorita}»: orientamento {rac['orientamento_id']}, "
                           f"variante {rac['variante']}. {rac['motivo'].capitalize()}.")
                variante = next((v for v in opt.get("varianti", [])
                                 if v["id"] == rac["variante_id"]), None)
                if variante:
                    base = dati.get("sezionamento", {}).get("processo", config.PROFILO_PROCESSO)
                    supporti = dati.get("sezionamento", {}).get("supporti", config.SUPPORTI_SEZIONAMENTO)
                    pezzo = Path(dati.get("file", cartella.name)).stem
                    nome_profilo = f"Assistente stampa - {pezzo} - {rac['variante']}"
                    profilo = slicer_cli.profilo_utente(
                        nome_profilo, base, variante["impostazioni"], supporti,
                    )
                    nome_base = nome_file_sicuro(f"{pezzo}_{rac['variante_id']}")
                    c_profilo, c_stl = st.columns(2)
                    c_profilo.download_button(
                        "Scarica profilo ElegooSlicer",
                        json.dumps(profilo, ensure_ascii=False, indent=2),
                        file_name=f"{nome_base}.json",
                        mime="application/json",
                    )
                    orientato = stl_raccomandato(cartella, rac, opt.get("varianti", []))
                    if orientato:
                        c_stl.download_button(
                            f"Scarica STL orientamento {rac['orientamento_id']}",
                            orientato.read_bytes(),
                            file_name=f"{nome_base}_orientamento_{rac['orientamento_id']}.stl",
                            mime="model/stl",
                        )
                    st.caption("Importa il JSON in ElegooSlicer come configurazione di processo. "
                               "Lo STL è già ruotato e appoggiato sul piatto nell'orientamento consigliato.")
                    riga_scelta = next((r for r in opt.get("risultati", [])
                                        if r["orientamento_id"] == rac["orientamento_id"]
                                        and r["variante_id"] == rac["variante_id"]), None)
                    materiale_g = (riga_scelta or {}).get("materiale_g")
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
                                        f"restano circa {migliore_bobina['margine_g']:g} g{costo_testo}.")
                            else:
                                st.warning(f"Nessuna bobina {materiale_bobina or ''} registrata contiene i "
                                           f"{materiale_g:g} g necessari.")
                        else:
                            st.caption("Registra una bobina nella scheda Bobine per verificare disponibilità e costo.")
            righe_varianti = []
            for r in opt.get("risultati", []):
                righe_varianti.append({
                    "orientamento": r["orientamento_id"], "variante": r["variante"],
                    "layer mm": r["layer_height"], "pareti": r["wall_loops"],
                    "riempimento": r["sparse_infill_density"], "tempo": r.get("tempo"),
                    "materiale g": r.get("materiale_g"), "supporti g": r.get("supporti_g"),
                    "Δ tempo %": r.get("delta_tempo_pct"), "Δ materiale %": r.get("delta_materiale_pct"),
                    "errore": r.get("errore"),
                })
            tabella_varianti = pd.DataFrame(righe_varianti)
            if "errore" in tabella_varianti and tabella_varianti["errore"].isna().all():
                tabella_varianti = tabella_varianti.drop(columns=["errore"])
            st.dataframe(tabella_varianti, width="stretch", hide_index=True)
            st.caption("I delta sono calcolati rispetto a Bilanciato sullo stesso orientamento. La scelta per superficie, "
                       "precisione o robustezza privilegia Dettaglio; velocità e materiale usano i valori misurati.")

        st.subheader("4. Consiglio di Claude")
        if st.button("Chiedi a Claude come stamparlo", type="primary"):
            richiesta = {"scopo": scopo, "tipo": uso, "priorita": priorita, "condizioni": ambiente,
                         "filamenti_disponibili": filamenti, "multimateriale_per_supporti": multimateriale, "note": note}
            richiesta.update({"sollecitazione": sollecitazione, "direzione_carico": direzione_carico,
                              "parte_critica": parte_critica})
            immagini = [str(p) for p in immagini_lavoro(cartella, dati)]
            with st.spinner("Claude sta guardando il pezzo (circa 1-2 minuti)..."):
                testo, costo, errore = chiedi(prompt_consiglio(dati, richiesta, immagini), cartella, modello)
            if errore or not testo:
                st.error(f"Qualcosa è andato storto: {errore or 'risposta vuota'}")
            else:
                (cartella / "richiesta.json").write_text(json.dumps(richiesta, ensure_ascii=False, indent=2), encoding="utf-8")
                (cartella / "consiglio.md").write_text(testo, encoding="utf-8")
                n = orientamento_scelto(testo)
                o = next((o for o in dati["orientamenti"] if o["id"] == n), None)
                (cartella / "consiglio.json").write_text(json.dumps({
                    "scelta_id": n,
                    "su": orienta_slicer.direzione_su(o["trasformazione"]).round(4).tolist() if o else None,
                    "modello": modello, "costo_usd": costo,
                }), encoding="utf-8")
        if (cartella / "consiglio.md").exists():
            st.markdown((cartella / "consiglio.md").read_text(encoding="utf-8"))
            info = json.loads((cartella / "consiglio.json").read_text(encoding="utf-8"))                 if (cartella / "consiglio.json").exists() else {}
            if info.get("costo_usd") is not None:
                st.caption(f"Modello {info.get('modello')}, equivalente API: {info['costo_usd']:.3f} $")
            st.info("Dopo la stampa annota com'è andata nella scheda **Diario di stampa**: "
                    "le prossime analisi ne terranno conto.")

# ------------------------------------------------------------------ diario
with tab_diario:
    st.subheader("Annota una stampa")
    lavori = sorted((p.name for p in config.LAVORI.iterdir() if p.is_dir()), reverse=True)
    with st.form("nuova_voce", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            pezzo = st.text_input("Pezzo")
            lavoro = st.selectbox("Analisi collegata", ["nessuna", *lavori])
            materiale = st.selectbox("Materiale", config.FILAMENTI)
            esito = st.select_slider("Esito", diario.ESITI, value="buona")
        with c2:
            problemi = st.multiselect("Problemi", diario.PROBLEMI)
            impostazioni = st.text_area("Impostazioni usate (quelle cambiate)", placeholder="es. strato 0,16; pareti 4; spaziatura interfaccia 0,2")
            commento = st.text_area("Com'è andata")
            foto = st.file_uploader("Foto (facoltative)", type=["jpg", "jpeg", "png"], accept_multiple_files=True)
        with st.expander("Parametri per la calibrazione personale"):
            p1, p2, p3 = st.columns(3)
            temperatura_ugello = p1.number_input("Temperatura ugello °C (0 = non annotata)", 0, 350, 0)
            temperatura_piatto = p2.number_input("Temperatura piatto °C (0 = non annotata)", 0, 150, 0)
            velocita_usata = p3.number_input("Velocità principale mm/s (0 = non annotata)", 0, 1000, 0)
            p4, p5, p6 = st.columns(3)
            flow_usato = p4.number_input("Flow % (0 = non annotato)", 0.0, 150.0, 0.0, step=0.5)
            retrazione_usata = p5.number_input("Retrazione mm (0 = non annotata)", 0.0, 20.0, 0.0, step=0.1)
            errore_dimensionale = p6.number_input(
                "Errore dimensionale mm (+ grande, − piccolo)", -10.0, 10.0, 0.0, step=0.05,
            )
        if st.form_submit_button("Salva nel diario", type="primary"):
            percorsi = []
            for f in foto or []:
                p = config.FOTO / f"{datetime.now():%Y%m%d-%H%M%S}_{f.name}"
                p.write_bytes(f.getvalue())
                percorsi.append(str(p))
            diario.aggiungi({"pezzo": pezzo, "analisi": None if lavoro == "nessuna" else lavoro, "materiale": materiale,
                             "esito": esito, "problemi": problemi, "impostazioni": impostazioni,
                             "commento": commento, "foto": percorsi,
                             "temperatura_ugello_c": temperatura_ugello,
                             "temperatura_piatto_c": temperatura_piatto,
                             "velocita_mm_s": velocita_usata, "flow_pct": flow_usato,
                             "retrazione_mm": retrazione_usata,
                             "errore_dimensionale_mm": errore_dimensionale})
            st.success("Salvato.")

    st.subheader("Stampe annotate")
    voci = diario.tutte()
    if not voci:
        st.caption("Ancora nessuna stampa nel diario.")
    else:
        st.markdown("**Tendenze registrate**")
        riepilogo_diario = calibrazione.analizza(voci)
        if riepilogo_diario["problemi_ricorrenti"]:
            st.dataframe(pd.DataFrame(riepilogo_diario["problemi_ricorrenti"]), width="stretch", hide_index=True)
        else:
            st.caption("Nessun problema compare ancora almeno due volte.")
    for i in reversed(range(len(voci))):
        v = voci[i]
        with st.expander(f"{v['data']} — {v.get('pezzo') or 'senza nome'} — {v['esito']}"):
            st.write({k: v[k] for k in ("materiale", "problemi", "impostazioni", "commento") if v.get(k)})
            for p in v.get("foto", []):
                st.image(p, width=320)
            if v.get("diagnosi"):
                st.markdown(v["diagnosi"])
            elif st.button("Chiedi a Claude cosa migliorare", key=f"diag{i}"):
                with st.spinner("Claude sta guardando la stampa..."):
                    testo, _, errore = chiedi(prompt_diagnosi(v, v.get("foto", [])), config.CARTELLA, modello)
                if errore or not testo:
                    st.error(f"Qualcosa è andato storto: {errore or 'risposta vuota'}")
                else:
                    diario.aggiorna(i, {"diagnosi": testo})
                    st.rerun()

# ------------------------------------------------------------------ bobine
with tab_bobine:
    st.subheader("Inventario bobine")
    inventario = bobine.tutte()
    if inventario:
        st.dataframe(pd.DataFrame([{
            "nome": b["nome"], "materiale": b["materiale"], "marca": b.get("marca"),
            "colore": b.get("colore"), "residuo g": b["residuo_g"],
            "tara g": b.get("tara_g"), "costo €": b.get("costo_eur"), "stato": b.get("stato"),
        } for b in inventario]), width="stretch", hide_index=True)
    else:
        st.caption("Nessuna bobina registrata.")

    with st.form("aggiungi_bobina", clear_on_submit=True):
        st.markdown("**Aggiungi una bobina**")
        b1, b2, b3 = st.columns(3)
        nome_bobina = b1.text_input("Nome bobina", placeholder="es. PETG nero Elegoo")
        materiale_bobina = b2.selectbox("Materiale", config.FILAMENTI, key="materiale_bobina")
        marca_bobina = b3.text_input("Marca")
        b4, b5, b6 = st.columns(3)
        colore_bobina = b4.text_input("Colore")
        peso_bobina = b5.number_input("Peso netto iniziale g", 1.0, 10000.0, 1000.0)
        residuo_bobina = b6.number_input("Residuo stimato g", 0.0, 10000.0, 1000.0)
        b7, b8, b9 = st.columns(3)
        tara_bobina = b7.number_input("Tara bobina vuota g", 0.0, 2000.0, 0.0)
        costo_bobina = b8.number_input("Costo bobina €", 0.0, 1000.0, 0.0, step=0.5)
        stato_bobina = b9.selectbox("Stato", ["pronta", "da essiccare", "esaurita"])
        if st.form_submit_button("Aggiungi bobina", type="primary"):
            bobine.aggiungi({
                "nome": nome_bobina, "materiale": materiale_bobina, "marca": marca_bobina,
                "colore": colore_bobina, "peso_netto_g": peso_bobina, "residuo_g": residuo_bobina,
                "tara_g": tara_bobina, "costo_eur": costo_bobina, "stato": stato_bobina,
            })
            st.rerun()

    if inventario:
        etichette_bobine = {f"{b['nome']} — {b['residuo_g']:g} g": b["id"] for b in inventario}
        c_consumo, c_pesata = st.columns(2)
        with c_consumo.form("consumo_bobina"):
            st.markdown("**Registra una stampa**")
            scelta_consumo = st.selectbox("Bobina", list(etichette_bobine), key="bobina_consumo")
            grammi_consumati = st.number_input("Grammi consumati", 0.0, 10000.0, 0.0, step=1.0)
            if st.form_submit_button("Sottrai dal residuo"):
                bobine.consuma(etichette_bobine[scelta_consumo], grammi_consumati)
                st.rerun()
        with c_pesata.form("pesata_bobina"):
            st.markdown("**Aggiorna con una pesata**")
            scelta_pesata = st.selectbox("Bobina", list(etichette_bobine), key="bobina_pesata")
            peso_lordo = st.number_input("Peso lordo bobina + filamento g", 0.0, 12000.0, 0.0, step=1.0)
            if st.form_submit_button("Calcola il residuo dalla tara"):
                bobine.aggiorna_da_pesata(etichette_bobine[scelta_pesata], peso_lordo)
                st.rerun()

# ------------------------------------------------------------------ storico
with tab_storico:
    st.caption("Ogni analisi è salvata con immagini, sezionamenti e consiglio di Claude: riaprirla non ricalcola niente.")
    salvati = {l["cartella"].name: l["dati"] for l in lavori_salvati()}
    for nome in sorted((p.name for p in config.LAVORI.iterdir() if p.is_dir()), reverse=True):
        cartella = config.LAVORI / nome
        if nome not in salvati:
            st.caption(f"{nome}: analisi interrotta prima del salvataggio, non si può riaprire.")
            continue
        with st.expander(f"{nome[16:] or nome} — {descrivi_lavoro(cartella, salvati[nome])}"):
            if st.button("Riapri nella scheda Analizza", key=f"apri{nome}", type="primary"):
                apri_lavoro(cartella)
                st.rerun()
            if (cartella / "orientamenti.png").exists():
                st.image(str(cartella / "orientamenti.png"))
            if (cartella / "consiglio.md").exists():
                st.markdown((cartella / "consiglio.md").read_text(encoding="utf-8"))
