"""Configurazione attiva del banco di lavoro, senza modificare i servizi locali."""
from html import escape

import streamlit as st

import augura_addon
import config
import slicer_cli
import ui


def valori_attivi():
    """Legge la configurazione senza montare i widget delle impostazioni."""
    provider = st.session_state.get("provider_ai", "Claude")
    modello = (st.session_state.get("modello_codex", "").strip() if provider == "Codex"
               else config.MODELLI[st.session_state.get("modello_claude", next(iter(config.MODELLI)))])
    filamenti = slicer_cli.filamenti_disponibili() if slicer_cli.disponibile() else []
    profilo = st.session_state.get("profilo_filamento", config.PROFILO_FILAMENTO)
    if filamenti and profilo not in filamenti:
        profilo = config.PROFILO_FILAMENTO if config.PROFILO_FILAMENTO in filamenti else filamenti[0]
    return provider, modello, bool(filamenti), profilo, augura_addon.disponibile()


def mostra():
    """Restituisce provider, modello, disponibilità slicer, profilo e disponibilità augura."""
    ui.barra_intestazione("impostazioni", testo="")
    ui.titolo_sezione(
        "IMPOSTAZIONI", "Il tuo banco di lavoro.",
        "Stampante, slicer e assistente: controlla qui la configurazione attiva.")
    profilo_filamento = config.PROFILO_FILAMENTO

    with st.container(key="impostazioni_layout"):
        principale, laterale = st.columns([926, 450], gap="large")
        with principale:
            with st.container(key="impostazioni_ai", border=True):
                st.subheader("Assistente AI")
                assistente, opzioni = st.columns(2, gap="large")
                with assistente:
                    provider = st.selectbox("Assistente AI", ["Claude", "Codex"], key="provider_ai")
                with opzioni:
                    if provider == "Codex":
                        if st.session_state.get("modello_codex", "") not in config.MODELLI_CODEX:
                            st.session_state["modello_codex"] = ""
                        modello = st.selectbox(
                            "Modello Codex", list(config.MODELLI_CODEX), key="modello_codex",
                            format_func=config.MODELLI_CODEX.__getitem__,
                            help="Scegli un modello o usa il predefinito della CLI. "
                                 "La disponibilità dipende dal tuo account Codex.")
                    else:
                        modello = config.MODELLI[st.selectbox("Modello di Claude", list(config.MODELLI), key="modello_claude")]
                if provider == "Codex":
                    from codex_ai import eseguibile
                    st.caption("Usa le credenziali locali di Codex CLI. Le richieste contano sui limiti o sulla "
                               "fatturazione dell’autenticazione attiva. Nessun invio prima della tua richiesta.")
                    if not eseguibile():
                        st.warning("Codex CLI non trovato: installalo oppure imposta STRATO_CODEX_EXE.")
                    st.caption("Se necessario, accedi dal terminale con: codex login")
                else:
                    st.caption("Usa il login di Claude Code di questo PC: con l'abbonamento non c'è costo extra, "
                               "conta sui limiti d'uso. Il costo mostrato è l'equivalente API.")

            with st.container(key="impostazioni_slicer", border=True):
                st.subheader("Sezionamento reale")
                SLICER = slicer_cli.disponibile()
                if SLICER:
                    filamenti_slicer = slicer_cli.filamenti_disponibili()
                    if filamenti_slicer:
                        if st.session_state.get("profilo_filamento") not in filamenti_slicer:
                            st.session_state["profilo_filamento"] = (config.PROFILO_FILAMENTO
                                if config.PROFILO_FILAMENTO in filamenti_slicer else filamenti_slicer[0])
                        profilo_filamento = st.selectbox("Profilo filamento", filamenti_slicer,
                                                        key="profilo_filamento")
                    else:
                        SLICER = False
                        st.warning("Nessun profilo filamento compatibile trovato: niente sezionamento reale.")
                else:
                    st.caption("ElegooSlicer non trovato: niente sezionamento reale.")
                with st.expander("Percorsi dello slicer"):
                    st.html(
                        '<dl class="strato-technical">'
                        f'<dt>Eseguibile</dt><dd><code>{escape(str(slicer_cli.ESEGUIBILE))}</code></dd>'
                        f'<dt>Profili</dt><dd><code>{escape(str(slicer_cli.PROFILI))}</code></dd></dl>')
                    st.caption("Per cambiarli imposta STRATO_SLICER_EXE e STRATO_SLICER_PROFILES prima di avviare l’app.")
                if SLICER:
                    st.caption(f"ElegooSlicer seziona ogni orientamento con «{config.PROFILO_PROCESSO}» e supporti ad albero "
                               f"solo dal piatto (soglia {config.SOGLIA_SUPPORTI}°): grammi e tempi veri, non stime.")

        with laterale:
            with st.container(key="impostazioni_stampante", border=True):
                st.subheader("Stampante")
                volume = " × ".join(str(v) for v in config.VOLUME_STAMPA) + " mm"
                righe = [("Modello", config.STAMPANTE["modello"]),
                         ("Ugello", config.STAMPANTE["ugello"]), ("Volume", volume)]
                st.html("".join(f'<div class="summary-row"><span>{escape(etichetta)}</span>'
                                f'<span>{escape(str(valore))}</span></div>' for etichetta, valore in righe))
                with st.expander("Dettagli della stampante"):
                    st.html("".join(
                        f'<div class="summary-row"><span>{escape(chiave.replace("_", " ").capitalize())}</span>'
                        f'<span>{escape(str(valore))}</span></div>'
                        for chiave, valore in config.STAMPANTE.items() if chiave not in {"modello", "ugello"}))

            with st.container(key="impostazioni_augura", border=True):
                st.subheader("Add-on augura")
                st.html('<span class="r-badge">FACOLTATIVO</span>')
                st.markdown("**STEP e controlli dedicati**")
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

    with st.container(border=True):
        st.caption("Le opzioni disponibili seguono i programmi e le credenziali presenti sul PC.")
    return provider, modello, SLICER, profilo_filamento, ADDON
