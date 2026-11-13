"""Inventario bobine: registrazione, consumi e pesate."""
import pandas as pd
import streamlit as st

import bobine
import config
import ui


def mostra():
    inventario = bobine.tutte()
    with st.container(key="bobine_layout"):
        with st.form("aggiungi_bobina", clear_on_submit=True, border=False):
            _, _, avanti = ui.barra_intestazione(
                "bobine", testo="Registra costo e tara solo se li conosci.")
            aggiungi = avanti.form_submit_button("Aggiungi bobina", type="primary", width="stretch")
            with st.container(key="bobine_titolo"):
                ui.titolo_sezione("BOBINE", "Le tue bobine",
                                  "Tieni sotto controllo materiale disponibile, consumo e costo.")
            with st.container(key="bobine_main"):
                with st.container(key="bobine_inventario", border=True):
                    st.subheader("Inventario")
                    if inventario:
                        st.dataframe(pd.DataFrame([{
                            "nome": b["nome"], "materiale": b["materiale"], "marca": b.get("marca"),
                            "colore": b.get("colore"), "residuo g": b["residuo_g"],
                            "tara g": b.get("tara_g"), "costo €": b.get("costo_eur"), "stato": b.get("stato"),
                        } for b in inventario]), width="stretch", hide_index=True)
                    else:
                        st.caption("Nessuna bobina registrata.")
                        st.caption("Aggiungi una bobina per verificare il materiale necessario alle prossime stampe.")
                with st.container(key="bobine_form", border=True):
                    st.subheader("Aggiungi una bobina")
                    nome, materiale = st.columns(2)
                    nome_bobina = nome.text_input("Nome bobina", placeholder="es. PETG nero Elegoo")
                    materiale_bobina = materiale.selectbox("Materiale", config.FILAMENTI, key="materiale_bobina")
                    marca, colore, stato = st.columns(3)
                    marca_bobina = marca.text_input("Marca")
                    colore_bobina = colore.text_input("Colore")
                    stato_bobina = stato.selectbox("Stato", ["pronta", "da essiccare", "esaurita"])
                    peso, residuo = st.columns(2)
                    peso_bobina = peso.number_input("Peso netto iniziale g", 1.0, 10000.0, 1000.0, step=1.0, format="%g")
                    residuo_bobina = residuo.number_input("Residuo stimato g", 0.0, 10000.0, 1000.0, step=1.0, format="%g")
                    tara, costo = st.columns(2)
                    tara_bobina = tara.number_input("Tara bobina vuota g", 0.0, 2000.0, 0.0, step=1.0, format="%g")
                    costo_bobina = costo.number_input("Costo bobina €", 0.0, 1000.0, 0.0, step=0.5)
            if aggiungi:
                bobine.aggiungi({
                    "nome": nome_bobina, "materiale": materiale_bobina, "marca": marca_bobina,
                    "colore": colore_bobina, "peso_netto_g": peso_bobina, "residuo_g": residuo_bobina,
                    "tara_g": tara_bobina, "costo_eur": costo_bobina, "stato": stato_bobina,
                })
                st.rerun()

        # I form di consumo e pesata devono essere fratelli del form di aggiunta.
        with st.container(key="bobine_aside"):
            with st.container(key="bobine_aggiorna", border=True):
                st.subheader("Aggiorna il residuo")
                if inventario:
                    etichette = {f"{b['nome']} — {b['residuo_g']:g} g [{b['id']}]": b["id"] for b in inventario}
                    with st.form("consumo_bobina", border=False):
                        st.markdown("**Registra una stampa**")
                        scelta_consumo = st.selectbox("Bobina", list(etichette), key="bobina_consumo")
                        grammi = st.number_input("Grammi consumati", 0.0, 10000.0, 0.0, step=1.0, format="%g")
                        if st.form_submit_button("Sottrai dal residuo", width="stretch"):
                            bobine.consuma(etichette[scelta_consumo], grammi)
                            st.rerun()
                    st.divider()
                    with st.form("pesata_bobina", border=False):
                        st.markdown("**Aggiorna con una pesata**")
                        scelta_pesata = st.selectbox("Bobina", list(etichette), key="bobina_pesata")
                        peso_lordo = st.number_input("Peso lordo bobina + filamento g", 0.0, 12000.0, 0.0, step=1.0, format="%g")
                        if st.form_submit_button("Calcola il residuo dalla tara", width="stretch"):
                            bobine.aggiorna_da_pesata(etichette[scelta_pesata], peso_lordo)
                            st.rerun()
                else:
                    st.markdown("**Registra una stampa**")
                    st.caption("Sottrai i grammi consumati dalla bobina.")
                    st.divider()
                    st.markdown("**Aggiorna con una pesata**")
                    st.caption("Usa peso lordo e tara della bobina.")
            with st.container(key="bobine_costi", border=True):
                st.subheader("Materiale e costi")
                st.caption("La configurazione selezionata nel risultato verifica le bobine compatibili, "
                           "il consumo previsto e la riserva.")
