"""Presentazione STRATO: stile e navigazione, senza logica di analisi."""
from base64 import b64encode
from functools import lru_cache
from html import escape
from pathlib import Path

import streamlit as st


def imposta_stile():
    st.html(f"<style>{Path(__file__).with_name('ui.css').read_text(encoding='utf-8')}</style>")


@lru_cache(maxsize=1)
def _font_caricamento():
    font = Path(__file__).parent / "assets" / "PlusJakartaSans-Variable.ttf"
    return b64encode(font.read_bytes()).decode("ascii")


def stile_caricamento():
    css = Path(__file__).with_name("caricamento.css").read_text(encoding="utf-8")
    st.html(f"""<style>@font-face {{ font-family:'Plus Jakarta Sans'; font-weight:200 800;
        src:url(data:font/ttf;base64,{_font_caricamento()}) format('truetype'); }}{css}</style>""")


def intestazione(stampante):
    st.html(f'''<header class="upload-header" hidden><b>STRATO°</b></header>
        <header class="strato-header"><div class="strato-brand">STRATO<span>°</span>
        <small>ASSISTENTE DI STAMPA 3D</small></div>
        <div class="strato-status"><span>STUDIO / 02</span> ● Locale · {escape(stampante)}</div></header>''')


def vai_fase(fase):
    st.session_state['fase_ui'] = fase


def percorso(fase, ha_lavoro):
    st.html('<div class="percorso-etichetta">IL PERCORSO DEL TUO PEZZO'
            + ('<span>Fase 01 di 06</span>' if fase == 1 else '') + '</div>')
    with st.container(key="percorso"):
        for n, (colonna, nome) in enumerate(zip(st.columns(6),
                ("Pezzo", "Utilizzo", "Priorità", "Riepilogo", "Analisi", "Risultato")), 1):
            colonna.button(f"{'✓' if n < fase else f'{n:02}'} · {nome}",
                key=f"fase_{n}", width="stretch", type="primary" if n == fase else "secondary",
                disabled=n == 5 or (n == 6 and not ha_lavoro) or
                         (n in (2, 3, 4) and not st.session_state.get('modello_ui')),
                on_click=vai_fase, args=(n,))


def titolo_fase(fase):
    titoli = {2: ("Raccontaci come lo userai.", "Funzione, ambiente e vincoli aiutano a interpretare i numeri."),
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
                azione.button("Rimuovi modello", key="rimuovi_modello",
                              help="Rimuovi il file per caricare un altro modello",
                              on_click=rimuovi_modello)
            anteprima_modello(file, key="modello3d_caricamento")
        else:
            formati = ["stl", "3mf", "obj"] + (["step", "stp"] if addon else [])
            limite = int(st.get_option("server.maxUploadSize"))
            st.html(f'''<div class="upload-stage">
                <div class="upload-meta"><span>STRATO° / MODELLO</span><span>MAX FILE: {limite} MB</span></div>
                <div class="upload-cube" aria-hidden="true"></div>
                <strong>Trascina qui il file 3D oppure sfoglia i file</strong>
                <div class="upload-description">Il modello resta sul tuo PC durante l’analisi geometrica e lo slicing.</div>
                <div class="upload-cta" aria-hidden="true">Seleziona file dal computer</div>
                <div class="upload-formats"><span>STL</span><span>3MF</span><span>OBJ</span><span>STEP*</span>
                <small>fino a {limite} MB</small></div>
                <div class="upload-footnote">* STEP/STP richiede l’add-on augura.</div></div>''')
            st.file_uploader("Seleziona file dal computer", type=formati, key="upload_ui",
                             on_change=carica_modello, label_visibility="collapsed")


def titolo_caricamento(stampante):
    modello = escape(stampante["modello"].removeprefix("Elegoo "))
    ugello = escape(stampante["ugello"])
    st.html(f'''<div class="upload-title"><div><h1>Carica il modello 3D</h1>
        <p>Importa il pezzo per confrontare orientamenti, tempi e consumo di filamento.</p></div>
        <div class="upload-profile"><small>PROFILO STAMPANTE</small><b>{modello} · ugello {ugello}</b></div></div>''')


def piatto_caricamento(stampante, volume):
    dimensioni = " × ".join(str(v) for v in volume)
    st.html(f'''<section class="upload-panel upload-bed"><h2>Piatto di stampa</h2>
        <div class="upload-volume"><small>VOLUME UTILE</small>
        <span>{dimensioni} mm</span></div>
        <dl><div><dt>Stampante</dt><dd>{escape(stampante["modello"])}</dd></div>
        <div><dt>Ugello</dt><dd>{escape(stampante["ugello"])}</dd></div></dl></section>''')


def azioni_caricamento(file):
    with st.container(key="upload_actions"):
        back, studio, status, next_step = st.columns([124, 696, 235, 235], gap="small")
        back.button("← Indietro", disabled=True, key="percorso_indietro", width="stretch")
        studio.html('<div class="upload-studio">Studio 02 · Analisi locale</div>')
        stato = "FILE SELEZIONATO" if file else "NESSUN FILE SELEZIONATO"
        dettaglio = escape(file.name) if file else "Carica un modello per continuare"
        status.html(f'<div class="upload-state"><small>{stato}</small><span>{dettaglio}</span></div>')
        next_step.button("Continua a Utilizzo →", type="primary", disabled=not file,
                         on_click=vai_fase, args=(2,), key="percorso_avanti", width="stretch")


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
