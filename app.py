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
import classifica
import config
import diario
import orienta_slicer
import slicer_cli
from consiglio import chiedi, orientamento_scelto, prompt_consiglio, prompt_diagnosi

st.set_page_config(page_title="Assistente stampa 3D", page_icon="🧩", layout="wide")
for d in (config.LAVORI, config.FOTO):
    d.mkdir(exist_ok=True)

# campi del modulo "Il pezzo e cosa ti serve": salvati in richiesta.json e ripristinati alla riapertura
CAMPI_RICHIESTA = {"scopo": "scopo", "tipo": "uso", "priorita": "priorita", "condizioni": "ambiente",
                   "filamenti_disponibili": "filamenti", "multimateriale_per_supporti": "multimateriale",
                   "note": "note"}
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

tab_analisi, tab_diario, tab_storico = st.tabs(["Analizza un pezzo", "Diario di stampa", "Analisi passate"])


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
            avviso = st.info("Il sezionamento richiede circa un minuto per orientamento: non toccare la pagina finché non finisce.")
            n = len(dati["orientamenti"])
            barra = st.progress(0.0, text=f"ElegooSlicer seziona {n} orientamenti...")

            def avanzamento(i, o):
                barra.progress(i / n, text=f"ElegooSlicer seziona l'orientamento {o['id']} ({i + 1} di {n})...")

            slicer_cli.seziona_orientamenti(mesh, dati["orientamenti"], cartella / "sezionamenti",
                                            config.PROFILO_PROCESSO, profilo_filamento,
                                            config.SUPPORTI_SEZIONAMENTO, avanzamento)
            classifica.applica(dati)
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

        st.subheader("3. Consiglio di Claude")
        if st.button("Chiedi a Claude come stamparlo", type="primary"):
            richiesta = {"scopo": scopo, "tipo": uso, "priorita": priorita, "condizioni": ambiente,
                         "filamenti_disponibili": filamenti, "multimateriale_per_supporti": multimateriale, "note": note}
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
        if st.form_submit_button("Salva nel diario", type="primary"):
            percorsi = []
            for f in foto or []:
                p = config.FOTO / f"{datetime.now():%Y%m%d-%H%M%S}_{f.name}"
                p.write_bytes(f.getvalue())
                percorsi.append(str(p))
            diario.aggiungi({"pezzo": pezzo, "analisi": None if lavoro == "nessuna" else lavoro, "materiale": materiale,
                             "esito": esito, "problemi": problemi, "impostazioni": impostazioni,
                             "commento": commento, "foto": percorsi})
            st.success("Salvato.")

    st.subheader("Stampe annotate")
    voci = diario.tutte()
    if not voci:
        st.caption("Ancora nessuna stampa nel diario.")
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
