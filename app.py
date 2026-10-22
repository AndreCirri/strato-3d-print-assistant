"""Assistente di stampa 3D. Avvio:  streamlit run app.py"""
import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

import augura_addon
import config
import diario
from analisi import analizza
from consiglio import chiedi, prompt_consiglio, prompt_diagnosi
from render import griglia_orientamenti, viste

st.set_page_config(page_title="Assistente stampa 3D", page_icon="🧩", layout="wide")
for d in (config.LAVORI, config.FOTO):
    d.mkdir(exist_ok=True)

with st.sidebar:
    st.header("Impostazioni")
    modello = config.MODELLI[st.selectbox("Modello di Claude", list(config.MODELLI))]
    st.caption("Usa il login di Claude Code di questo PC: con l'abbonamento non c'è costo extra, "
               "conta sui limiti d'uso. Il costo mostrato è l'equivalente API.")
    st.subheader("Stampante")
    st.json(config.STAMPANTE, expanded=False)
    st.subheader("Add-on")
    ADDON = augura_addon.disponibile()
    if ADDON:
        st.success("augura attivo: file STEP e controlli in più")
    else:
        st.caption("augura non installato. Per file STEP e controlli esatti: "
                   "`addon_augura\\installa.bat` (circa 700 MB), poi riavvia.")

tab_analisi, tab_diario, tab_storico = st.tabs(["Analizza un pezzo", "Diario di stampa", "Analisi passate"])


def nome_lavoro(nome_file):
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(nome_file).stem)[:40]
    return f"{datetime.now():%Y%m%d-%H%M%S}_{base}"


# ------------------------------------------------------------------ analisi
with tab_analisi:
    st.subheader("1. Il pezzo e cosa ti serve")
    formati = ["stl", "3mf", "obj"] + (["step", "stp"] if ADDON else [])
    file = st.file_uploader("File da stampare", type=formati)
    c1, c2 = st.columns(2)
    with c1:
        scopo = st.text_area("A cosa serve, dove va montato",
                             placeholder="es. pulsante della lavatrice: la linguetta fa da molla, il perno preme l'interruttore")
        uso = st.selectbox("Tipo di pezzo", ["funzionale / meccanico", "estetico", "prototipo veloce", "misto"])
        priorita = st.selectbox("Cosa conta di più", ["robustezza e rigidità", "superficie bella", "precisione delle misure",
                                                      "velocità di stampa", "poco materiale"])
    with c2:
        ambiente = st.multiselect("Condizioni d'uso", ["caldo oltre 50 °C", "umidità o acqua", "all'aperto (sole)",
                                                       "sforzi ripetuti / flessione", "urti", "contatto con alimenti"])
        filamenti = st.multiselect("Filamenti che hai", config.FILAMENTI, default=["PLA", "PETG"])
        multimateriale = st.checkbox("Ho un sistema multimateriale (es. CANVAS) per l'interfaccia dei supporti")
        note = st.text_input("Altro (lato da tenere bello, problemi avuti, ecc.)")

    if file and st.button("Analizza la geometria", type="primary"):
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
            griglia_orientamenti(mesh, dati["orientamenti"], cartella / "orientamenti.png")
            for o in dati["orientamenti"][:2]:
                viste(mesh, o["trasformazione"], cartella / f"viste_{o['id']}.png",
                      f"Orientamento {o['id']} ({o['origine']})")
        if ADDON:
            with st.spinner("Controlli di augura..."):
                dati["augura"] = augura_addon.verifica(originale)
        (cartella / "analisi.json").write_text(json.dumps(dati, ensure_ascii=False, indent=2), encoding="utf-8")
        st.session_state["lavoro"] = str(cartella)

    if "lavoro" in st.session_state:
        cartella = Path(st.session_state["lavoro"])
        dati = json.loads((cartella / "analisi.json").read_text(encoding="utf-8"))
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
        tabella = pd.DataFrame([{k: v for k, v in o.items() if k != "trasformazione"} for o in dati["orientamenti"]])
        tabella["avvisi"] = tabella["avvisi"].apply(lambda a: "; ".join(a))
        st.dataframe(tabella.set_index("id"), width="stretch")
        st.caption("Punteggio più basso = meno supporti da togliere. I supporti che poggiano sul pezzo pesano il triplo.")
        st.image(str(cartella / "orientamenti.png"))
        for img in sorted(cartella.glob("viste_*.png")):
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
            immagini = [str(p) for p in [cartella / "orientamenti.png", *sorted(cartella.glob("viste_*.png"))]]
            with st.spinner("Claude sta guardando il pezzo (circa 1-2 minuti)..."):
                testo, costo, errore = chiedi(prompt_consiglio(dati, richiesta, immagini), cartella, modello)
            if errore or not testo:
                st.error(f"Qualcosa è andato storto: {errore or 'risposta vuota'}")
            else:
                (cartella / "richiesta.json").write_text(json.dumps(richiesta, ensure_ascii=False, indent=2), encoding="utf-8")
                (cartella / "consiglio.md").write_text(testo, encoding="utf-8")
                st.session_state["costo"] = costo
        if (cartella / "consiglio.md").exists():
            st.markdown((cartella / "consiglio.md").read_text(encoding="utf-8"))
            if st.session_state.get("costo") is not None:
                st.caption(f"Equivalente API: {st.session_state['costo']:.3f} $")
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
    for nome in sorted((p.name for p in config.LAVORI.iterdir() if p.is_dir()), reverse=True):
        cartella = config.LAVORI / nome
        with st.expander(nome):
            if (cartella / "orientamenti.png").exists():
                st.image(str(cartella / "orientamenti.png"))
            if (cartella / "consiglio.md").exists():
                st.markdown((cartella / "consiglio.md").read_text(encoding="utf-8"))
            else:
                st.caption("Solo analisi geometrica, nessun consiglio richiesto.")
            if st.button("Riapri nella scheda Analizza", key=f"apri{nome}"):
                st.session_state["lavoro"] = str(cartella)
                st.rerun()
