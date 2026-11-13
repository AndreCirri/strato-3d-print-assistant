"""Diario di stampa: modulo locale, foto e diagnosi su richiesta."""
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

import calibrazione
import config
import diario
import ui
from consiglio import chiedi, prompt_diagnosi


def mostra(provider, modello):
    lavori = sorted((p.name for p in config.LAVORI.iterdir() if p.is_dir()), reverse=True) \
        if config.LAVORI.exists() else []
    with st.container(key="diario_layout"):
        with st.form("nuova_voce", clear_on_submit=True, border=False):
            _, _, avanti = ui.barra_intestazione("diario", testo="I dati restano salvati in locale.")
            submit = avanti.form_submit_button("Salva nel diario", type="primary", width="stretch")
            with st.container(key="diario_titolo"):
                ui.titolo_sezione("Diario", "Diario di stampa",
                                  "Annota esito e impostazioni: le esperienze diventano confronti utili.")
            with st.container(key="diario_form", border=True):
                st.subheader("Annota una stampa")
                p1, p2 = st.columns(2)
                pezzo = p1.text_input("Pezzo", placeholder="Nome del pezzo")
                lavoro = p2.selectbox("Analisi collegata", ["nessuna", *lavori])
                p3, p4 = st.columns(2)
                materiale = p3.selectbox("Materiale", config.FILAMENTI)
                esito = p4.selectbox("Esito", diario.ESITI, index=diario.ESITI.index("buona"),
                                     format_func=str.capitalize)
                problemi = st.multiselect("Problemi", diario.PROBLEMI,
                                            placeholder="Seleziona eventuali problemi…")
                p5, p6 = st.columns(2)
                impostazioni = p5.text_area("Impostazioni usate (quelle cambiate)",
                    placeholder="es. strato 0,16; pareti 4; spaziatura interfaccia 0,2")
                commento = p6.text_area("Com’è andata", placeholder="Osservazioni sulla stampa…")
                foto = st.file_uploader("Foto facoltative", type=["jpg", "jpeg", "png"],
                                        accept_multiple_files=True)
                with st.expander("Parametri per la calibrazione personale"):
                    c1, c2, c3 = st.columns(3)
                    temperatura_ugello = c1.number_input("Temperatura ugello °C (0 = non annotata)", 0, 350, 0)
                    temperatura_piatto = c2.number_input("Temperatura piatto °C (0 = non annotata)", 0, 150, 0)
                    velocita_usata = c3.number_input("Velocità principale mm/s (0 = non annotata)", 0, 1000, 0)
                    c4, c5, c6 = st.columns(3)
                    flow_usato = c4.number_input("Flow % (0 = non annotato)", 0.0, 150.0, 0.0, step=0.5)
                    retrazione_usata = c5.number_input("Retrazione mm (0 = non annotata)", 0.0, 20.0, 0.0, step=0.1)
                    errore_dimensionale = c6.number_input(
                        "Errore dimensionale mm (+ grande, − piccolo)", -10.0, 10.0, value=None, step=0.05)
                    profilo_diario = st.text_input("Profilo filamento usato", value=config.PROFILO_FILAMENTO)

        if submit:
            try:
                percorsi = []
                for f in foto or []:
                    config.FOTO.mkdir(parents=True, exist_ok=True)
                    p = config.FOTO / f"{datetime.now():%Y%m%d-%H%M%S_%f}_{Path(f.name).name}"
                    p.write_bytes(f.getvalue())
                    percorsi.append(str(p))
                diario.aggiungi({
                    "pezzo": pezzo, "analisi": None if lavoro == "nessuna" else lavoro,
                    "materiale": materiale, "esito": esito, "problemi": problemi,
                    "impostazioni": impostazioni, "commento": commento, "foto": percorsi,
                    "temperatura_ugello_c": temperatura_ugello, "temperatura_piatto_c": temperatura_piatto,
                    "velocita_mm_s": velocita_usata, "flow_pct": flow_usato, "retrazione_mm": retrazione_usata,
                    "profilo_filamento": profilo_diario, "errore_dimensionale_mm": errore_dimensionale,
                })
            except OSError as errore:
                with st.container(key="diario_salvataggio"):
                    st.error(f"Salvataggio non riuscito: {errore}")
            else:
                with st.container(key="diario_salvataggio"):
                    st.success("Salvato.")

        # L’elenco è fuori dal form: le diagnosi non inviano né cancellano i campi.
        with st.container(key="diario_elenco", border=True):
            st.subheader("Le tue stampe")
            voci = diario.tutte()
            if not voci:
                st.caption("Ancora nessuna stampa nel diario.")
                st.caption("Dopo il primo salvataggio troverai qui esito, foto e diagnosi facoltative. "
                           "Le tendenze compaiono con osservazioni sufficienti.")
            else:
                with st.expander("Tendenze registrate"):
                    filtro_materiale = st.selectbox("Materiale per le tendenze", config.FILAMENTI,
                                                   key="materiale_tendenze")
                    profili = sorted({v.get("profilo_filamento") or "__non_annotato__" for v in voci
                                      if v.get("materiale") == filtro_materiale}) or ["__non_annotato__"]
                    filtro_profilo = st.selectbox("Profilo per le tendenze", profili,
                        format_func=lambda x: "Profilo non annotato" if x == "__non_annotato__" else x)
                    riepilogo = calibrazione.analizza(voci, filtro_materiale, profilo=filtro_profilo)
                    if riepilogo["problemi_ricorrenti"]:
                        st.dataframe(pd.DataFrame(riepilogo["problemi_ricorrenti"]),
                                     width="stretch", hide_index=True)
                    else:
                        st.caption("Nessun problema compare ancora almeno due volte.")
            for i in reversed(range(len(voci))):
                v = voci[i]
                with st.expander(f"{v['data']} — {v.get('pezzo') or 'senza nome'} — {v['esito']}"):
                    st.write({k: v[k] for k in ("materiale", "problemi", "impostazioni", "commento") if v.get(k)})
                    for p in v.get("foto", []):
                        if Path(p).is_file():
                            st.image(p, width=320)
                        else:
                            st.warning(f"Foto non disponibile: {Path(p).name}")
                    if v.get("diagnosi"):
                        st.markdown(v["diagnosi"])
                        st.caption(f"Diagnosi di {v.get('diagnosi_provider', 'Claude')}")
                    elif st.button(f"Chiedi a {provider} cosa migliorare", key=f"diag{i}", width="stretch"):
                        with st.spinner(f"{provider} sta guardando la stampa..."):
                            testo, _, errore = chiedi(prompt_diagnosi(v, v.get("foto", [])), config.CARTELLA,
                                                     modello, provider=provider, immagini=v.get("foto", []))
                        if errore or not testo:
                            st.error(f"Qualcosa è andato storto: {errore or 'risposta vuota'}")
                        else:
                            try:
                                diario.aggiorna(i, {"diagnosi": testo, "diagnosi_provider": provider,
                                                   "diagnosi_modello": modello or "predefinito"})
                            except OSError as errore:
                                st.error(f"Salvataggio della diagnosi non riuscito: {errore}")
                            else:
                                st.rerun()
