"""Presentazione STRATO: stile e navigazione, senza logica di analisi."""
from base64 import b64encode
from functools import lru_cache
from html import escape
from pathlib import Path

import streamlit as st


def imposta_stile():
    css = "\n".join(Path(__file__).with_name(nome).read_text(encoding="utf-8")
                    for nome in ("ui.css", "caricamento.css"))
    st.html(f"""<style>@font-face {{ font-family:'Plus Jakarta Sans'; font-weight:200 800;
        font-style:normal; font-display:swap;
        src:url(data:font/ttf;base64,{_font_caricamento()}) format('truetype'); }}
        html, body, .stApp {{ font-family:'Plus Jakarta Sans',sans-serif; }}
        {css}</style>""")


@lru_cache(maxsize=1)
def _font_caricamento():
    font = Path(__file__).parent / "assets" / "PlusJakartaSans-Variable.ttf"
    return b64encode(font.read_bytes()).decode("ascii")


def barra_intestazione(chiave, *, testo="Studio 02 · Analisi locale", stato=None):
    with st.container(key=f"header_{chiave}"):
        brand, studio, alternativa, indietro, avanti = st.columns(
            [180, 630, 235, 124, 235], gap="small", vertical_alignment="center")
        brand.html('<a class="strato-brand" href="?" target="_self" aria-label="STRATO — Torna alla home" title="Torna alla home"><span>STRATO°</span></a>')
        studio.html(f'<div class="strato-studio">{escape(testo)}</div>')
        if stato:
            titolo, dettaglio = stato if isinstance(stato, tuple) else (stato, "")
            alternativa.html(f'<div class="strato-header-stato"><small>{escape(titolo)}</small>'
                             f'<span>{escape(dettaglio)}</span></div>')
        return (indietro.container(key=f"header_{chiave}_indietro"),
                alternativa.container(key=f"header_{chiave}_alternativa"),
                avanti.container(key=f"header_{chiave}_avanti"))


def vai_fase(fase):
    st.session_state['fase_ui'] = fase


def percorso(fase, ha_lavoro):
    st.html('<div class="percorso-etichetta">IL PERCORSO DEL TUO PEZZO'
            f'<span>Fase {fase:02} di 06</span></div>')
    with st.container(key="percorso"):
        for n, (colonna, nome) in enumerate(zip(st.columns(6),
                ("Pezzo", "Utilizzo", "Priorità", "Riepilogo", "Analisi", "Risultato")), 1):
            stato = "completed" if n < fase else "active" if n == fase else "waiting"
            with colonna.container(key=f"passo_{n}_{stato}"):
                st.button(f"{n:02} · {nome}",
                    key=f"fase_{n}", width="stretch", type="primary" if n == fase else "secondary",
                    disabled=n == 5 or (n == 6 and not ha_lavoro) or
                             (n in (2, 3, 4) and not st.session_state.get('modello_ui')),
                    on_click=vai_fase, args=(n,))
                etichetta = {"completed": "Completato", "active": "In corso", "waiting": "In attesa"}[stato]
                st.html(f'<div class="percorso-stato">{etichetta}</div>')


def titolo_sezione(etichetta, titolo, sottotitolo):
    st.html(f'<div class="sezione-intestazione"><div class="strato-eyebrow">{escape(etichetta)}</div>'
            f'<h1>{escape(titolo)}</h1><p>{escape(sottotitolo)}</p></div>')


def titolo_fase(fase):
    titoli = {2: ("Raccontaci come lo userai.", "Funzione, ambiente e vincoli aiutano a interpretare i numeri."),
              3: ("Che cosa conta di più?", "Una priorità chiara rende più leggibili i compromessi."),
              4: ("Tutto pronto per l’analisi.", "Controlla le scelte prima di avviare il lavoro."),
              5: ("Il tuo pezzo prende forma.", "Analisi locale · puoi consultare diario e bobine durante l’attesa."),
              6: ("Dai dati alla tua prossima stampa.", "Confronta gli orientamenti e scegli la configurazione da esportare.")}
    titolo, testo = titoli[fase]
    st.html(f'<div class="fase-intestazione"><h1>{escape(titolo)}</h1>'
            f'<p>{escape(testo)}</p></div>')


def contesto_pezzo(file, stampante, filamenti, *, fase=None):
    fase = fase if fase is not None else st.session_state.get("fase_ui", 2)
    consigli = {
        2: ("Prima i dati, poi il consiglio", "Geometria e slicer costruiscono il confronto. Claude o Codex aggiungono una spiegazione solo quando lo chiedi."),
        3: ("Un confronto, più possibilità", "La ricerca varia un parametro per volta. Tempo e materiale vengono misurati; superficie e robustezza restano indicatori."),
        4: ("Cosa succede dopo", "1. Analisi geometrica\n2. Confronto degli orientamenti\n3. Tempi e consumi dello slicer\n4. Configurazioni esportabili"),
        5: ("Elaborazione riprendibile", "Puoi cambiare pagina durante il calcolo. Se il processo si interrompe, riprendi dai passaggi salvati."),
    }
    titolo, testo = consigli.get(fase, consigli[2])
    with st.container(key="wizard_aside"):
        with st.container(key="contesto_modello", border=True):
            st.subheader("Il tuo pezzo")
            if file:
                anteprima_modello(file, key="modello3d_contesto")
            else:
                st.html('<div class="strato-context"><div class="upload-cube" aria-hidden="true"></div></div>')
            nome = file.name if file else "Il tuo prossimo pezzo"
            st.html(f'<div class="strato-context-nome">{escape(nome)}</div>')
            st.caption("Modello caricato" if file else "Carica un modello per continuare")
            st.caption(f"{stampante['modello']} · ugello {stampante['ugello']}")
            if filamenti:
                st.caption(", ".join(filamenti))
        with st.container(key="contesto_consiglio", border=True):
            st.subheader(titolo)
            st.html(f'<p class="strato-context-consiglio">{escape(testo).replace(chr(10), "<br>")}</p>')


def contesto_utilizzo():
    st.subheader("Utilizzo del pezzo")


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


@st.cache_data(show_spinner=False, max_entries=8)
def _anteprima(contenuto, estensione):
    from anteprima import crea
    try:
        return crea(contenuto, estensione), None
    except Exception as errore:
        return None, str(errore)


def anteprima_modello(file, *, key="modello3d_mobile"):
    from visualizzatore import mostra
    contenuto = None
    try:
        contenuto = file.read_bytes() if isinstance(file, Path) else file.getvalue()
        mostra(contenuto, Path(file.name).suffix, key=key)
    except Exception as errore:
        immagine, dettaglio = (_anteprima(contenuto, Path(file.name).suffix)
                              if contenuto is not None else (None, str(errore)))
        if immagine:
            st.image(immagine, alt=f"Anteprima 3D di {file.name}", width="stretch")
            st.caption('Anteprima statica: visualizzatore 3D non disponibile.')
            return
        st.warning("Anteprima non disponibile. Controlla che il file contenga un modello 3D valido.")
        with st.expander("Dettaglio anteprima"):
            st.text(dettaglio or str(errore))
