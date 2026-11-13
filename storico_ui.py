"""Storico locale delle analisi, riaperte dai file senza nuovi calcoli."""
import streamlit as st

import config
import lavorazioni
import ui


def mostra(lavori_salvati, descrivi_lavoro, apri_lavoro, nuovo_pezzo):
    """Mostra lo storico usando i callback di lettura e riapertura dell’app."""
    ui.barra_intestazione("storico", testo="")
    ui.titolo_sezione(
        "STORICO", "Le analisi, sempre a portata di mano.",
        "Riprendi un lavoro o confronta una configurazione senza rifare i calcoli.")
    salvati = {l["cartella"].name: l["dati"] for l in lavori_salvati()}
    cartelle = sorted((p for p in config.LAVORI.iterdir() if p.is_dir()), reverse=True)

    with st.container(key="storico_elenco", border=True):
        st.subheader("Analisi salvate")
        if not cartelle:
            with st.container(key="storico_vuoto", border=False, height=466,
                              horizontal_alignment="center", vertical_alignment="center"):
                st.html('<div class="storico-vuoto-testo"><h2>Qui ritroverai i tuoi pezzi.</h2>'
                        '<p>Non ci sono ancora analisi salvate.</p></div>')
                st.button("Analizza un nuovo pezzo →", key="storico_nuovo_pezzo",
                          type="primary", on_click=nuovo_pezzo)
                st.caption("Lavori completati e lavorazioni interrotte saranno distinguibili.\n\n"
                           "Un lavoro già calcolato si riapre senza ripetere l’analisi.")
        else:
            st.caption("Ogni analisi è salvata con immagini, sezionamenti e consiglio AI: "
                       "riaprirla non ricalcola niente.")
            for cartella in cartelle:
                nome = cartella.name
                if nome not in salvati:
                    if (cartella / "ingresso.json").exists():
                        stato = lavorazioni.stato(cartella).get("stato")
                        etichetta = ("Analisi in corso" if stato == "in corso" else
                                     "Lavorazione interrotta" if stato in ("errore", "interrotta")
                                     else "Lavorazione da completare")
                        st.caption(f"{nome}: {etichetta}.")
                        st.button(f"Apri lavorazione {nome}", key=f"riprendi{nome}",
                                  on_click=apri_lavoro, args=(cartella,))
                    else:
                        st.caption(f"{nome}: analisi precedente interrotta prima del salvataggio.")
                    continue
                with st.expander(f"{nome[16:] or nome} — {descrivi_lavoro(cartella, salvati[nome])}"):
                    st.caption("Analisi completata · riapertura senza nuovi calcoli.")
                    st.button("Riapri nella pagina Analisi", key=f"apri{nome}", type="primary",
                              on_click=apri_lavoro, args=(cartella,))
                    if (cartella / "orientamenti.png").exists():
                        st.image(str(cartella / "orientamenti.png"))
                    if (cartella / "consiglio.md").exists():
                        st.markdown((cartella / "consiglio.md").read_text(encoding="utf-8"))

    with st.container(key="storico_persistenza", border=True):
        st.subheader("Salvataggio locale")
        st.caption("Modello, immagini, sezionamenti e consiglio restano collegati alla stessa analisi.")
