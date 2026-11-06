"""Presentazione STRATO: stile e navigazione, senza logica di analisi."""
from html import escape
from pathlib import Path

import streamlit as st


def imposta_stile():
    st.html(f"<style>{Path(__file__).with_name('ui.css').read_text(encoding='utf-8')}</style>")


def intestazione(stampante):
    st.html(f'''<header class="strato-header"><div class="strato-brand">STRATO<span>°</span>
        <small>ASSISTENTE DI STAMPA 3D</small></div>
        <div class="strato-status"><span>STUDIO / 02</span> ● Locale · {escape(stampante)}</div></header>''')


def vai_fase(fase):
    st.session_state['fase_ui'] = fase


def percorso(fase, ha_lavoro):
    st.html('<div class="percorso-etichetta">IL PERCORSO DEL TUO PEZZO</div>')
    with st.container(key="percorso"):
        for n, (colonna, nome) in enumerate(zip(st.columns(6),
                ("Pezzo", "Utilizzo", "Priorità", "Riepilogo", "Analisi", "Risultato")), 1):
            colonna.button(f"{'✓' if n < fase else f'{n:02}'} · {nome}",
                key=f"fase_{n}", width="stretch", type="primary" if n == fase else "secondary",
                disabled=n == 5 or (n == 6 and not ha_lavoro) or
                         (n in (2, 3, 4) and not st.session_state.get('modello_ui')),
                on_click=vai_fase, args=(n,))


def titolo_fase(fase):
    if fase == 1:
        st.html('<div class="fase-intestazione fase-modello"><h1>Carica il modello</h1></div>')
        return
    titoli = {1: ("Partiamo dal tuo pezzo.", "Un modello, qualche scelta. Al resto pensa il tuo banco di lavoro."),
              2: ("Raccontaci come lo userai.", "Funzione, ambiente e vincoli aiutano a interpretare i numeri."),
              3: ("Che cosa conta di più?", "Una priorità chiara rende più leggibili i compromessi."),
              4: ("Tutto pronto per l’analisi.", "Controlla le scelte prima di avviare il lavoro."),
              5: ("Il tuo pezzo prende forma.", "Analisi locale · puoi consultare diario e bobine durante l’attesa."),
              6: ("Dai dati alla tua prossima stampa.", "Confronta gli orientamenti e scegli la configurazione da esportare.")}
    titolo, testo = titoli[fase]
    st.html(f'<div class="fase-intestazione"><div class="strato-eyebrow">'
            f'{"NUOVA ANALISI" if fase < 5 else "ANALISI"} / {fase:02}</div>'
            f'<h1>{escape(titolo)}</h1><p>{escape(testo)}</p></div>')


def contesto_pezzo(file, stampante, filamenti):
    with st.container(key="wizard_aside"):
        if file:
            anteprima_modello(file, key="modello3d_contesto")
        else:
            st.html('''<div class="strato-context"><span class="strato-model-icon" aria-hidden="true">&#11041;</span></div>''')
        st.subheader(file.name if file else "Il tuo prossimo pezzo")
        st.caption(f"{stampante['modello']} · Ugello {stampante['ugello']}")
        st.caption(", ".join(filamenti) if filamenti else "Scegli i materiali nel passaggio Utilizzo.")
        st.divider()
        st.html('<div class="strato-eyebrow">PRIMA I DATI, POI IL CONSIGLIO</div>')
        st.caption("Geometria e slicer costruiscono il confronto. Claude aggiunge una spiegazione solo quando lo chiedi.")
    st.caption("L’analisi è locale. Le informazioni vengono inviate a Claude solo su richiesta esplicita.")


def contesto_utilizzo():
    st.subheader("Il contesto fa la differenza.")


def carica_modello():
    st.session_state['modello_ui'] = st.session_state.get('upload_ui')


def rimuovi_modello():
    st.session_state['modello_ui'] = None
    st.session_state.pop('upload_ui', None)


def selezione_modello(file, addon):
    with st.container(key="modello_box", border=True):
        if file:
            with st.container(key="modello_intestazione"):
                nome, azione = st.columns([12, 1])
                nome.write(file.name)
                azione.button("Rimuovi modello", icon=":material/close:", key="rimuovi_modello",
                              help="Rimuovi il file per caricare un altro modello",
                              on_click=rimuovi_modello)
            anteprima_modello(file, key="modello3d_caricamento")
        else:
            formati = ["stl", "3mf", "obj"] + (["step", "stp"] if addon else [])
            st.file_uploader("File da stampare", type=formati, key="upload_ui",
                             on_change=carica_modello, label_visibility="collapsed")


@st.cache_data(show_spinner=False, max_entries=8)
def _anteprima(contenuto, estensione):
    from anteprima import crea
    try:
        return crea(contenuto, estensione), None
    except Exception as errore:
        return None, str(errore)


def anteprima_modello(file, *, key="modello3d_mobile"):
    from visualizzatore import mostra
    try:
        mostra(file.getvalue(), Path(file.name).suffix, key=key)
    except Exception as errore:
        immagine, dettaglio = _anteprima(file.getvalue(), Path(file.name).suffix)
        if immagine:
            st.image(immagine, alt=f"Anteprima 3D di {file.name}", width="stretch")
            st.caption('Anteprima statica: visualizzatore 3D non disponibile.')
            return
        st.warning("Anteprima non disponibile. Controlla che il file contenga un modello 3D valido.")
        with st.expander("Dettaglio anteprima"):
            st.text(dettaglio or str(errore))
