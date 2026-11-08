"""Pagine di risultato STRATO, con selezione condivisa e download verificati."""
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

import calibrazione
import config
import confronto
import lavorazioni
import ottimizzazione
import stampabilita
from validazione import numero, riga_valida, risultato_valido


def grammi(valore):
    return f"{valore:.1f} g".replace('.', ',') if numero(valore) else 'n.d.'


def testo_profilo(testo):
    for prima, dopo in (('Ricerca sparse_infill_density', 'Riempimento'),
                        ('Ricerca wall_loops', 'Pareti'), ('Ricerca layer_height', 'Layer'),
                        ('sparse_infill_density', 'riempimento'), ('wall_loops', 'pareti'),
                        ('layer_height', 'altezza layer')):
        testo = testo.replace(prima, dopo)
    return testo


def nome_orientamento(o):
    origine = o.get('origine', 'Orientamento')
    return f"Appoggio stabile {o['id']:02}" if origine == 'posa stabile' else origine.capitalize()


def descrizione_orientamento(o):
    appoggio = o.get('area_appoggio_mm2')
    parti = [f"Appoggio {appoggio:g} mm²." if numero(appoggio) else 'Appoggio da verificare.']
    parti.append('Brim consigliato.' if o.get('brim_consigliato') else 'Confronta supporti e finitura.')
    return ' '.join(parti)


def tempo(riga):
    secondi = riga.get('tempo_s')
    if not numero(secondi):
        return riga.get('tempo') or 'n.d.'
    minuti = round(secondi / 60)
    return f"{minuti // 60} h {minuti % 60:02} min" if minuti >= 60 else f"{minuti} min"


def totale(riga):
    if numero(riga.get('consumo_totale_g')):
        return riga['consumo_totale_g']
    if all(numero(riga.get(k)) for k in ('pezzo_g', 'supporti_g', 'brim_g')):
        return sum(riga[k] for k in ('pezzo_g', 'supporti_g', 'brim_g'))
    return riga.get('materiale_g')


def delta(valore, riferimento):
    if not numero(valore) or not numero(riferimento) or riferimento <= 0:
        return 'n.d.'
    return f'{(valore / riferimento - 1) * 100:+.0f}%'


def badge(misurato=True, fonte=''):
    st.html(f'<span class="r-badge {"misurato" if misurato else "euristico"}">{"✓ Misurato" if misurato else "◇ Euristico"}</span><span class="r-fonte">{escape(fonte)}</span>')


def scheda(chiave, nome):
    st.session_state[chiave] = nome


def scegli(chiave, widget, scelta, navigazione, pagina='Risultato'):
    st.session_state[chiave] = scelta
    st.session_state[widget] = scelta
    st.session_state[navigazione] = pagina


def nuovo_pezzo():
    st.session_state['fase_ui'] = 1
    for chiave in ('modello_ui', 'upload_ui', 'lavoro'):
        st.session_state.pop(chiave, None)
    st.query_params.pop('lavoro', None)


def chiedi_consiglio(navigazione):
    st.session_state[navigazione] = 'Consiglio e apprendimento'
    st.session_state['richiedi_consiglio_ui'] = True


@st.cache_data(show_spinner=False, max_entries=40)
def immagine_orientata(percorso, modificato, trasformazione):
    from anteprima import crea
    p = Path(percorso)
    return crea(p.read_bytes(), p.suffix, trasformazione, sfondo='none', zoom=1.6)


def modello(percorso, orientamento, interattivo=False):
    if percorso and percorso.is_file():
        try:
            if interattivo:
                from visualizzatore import mostra
                mostra(percorso.read_bytes(), percorso.suffix, key=f"modello3d_risultato_{percorso.parent.name}",
                       trasformazione=orientamento.get('trasformazione'), supporti=True)
                return
            immagine = immagine_orientata(str(percorso), percorso.stat().st_mtime_ns,
                                         orientamento.get('trasformazione'))
            st.image(immagine, width='stretch',
                     alt=f"Modello nell’orientamento {orientamento['id']}")
        except Exception:
            st.info('Anteprima non disponibile per questo modello.')
    else:
        st.info('Il file originale non è disponibile. Riapri il modello per visualizzare l’anteprima.')


def metriche(riga, mini=False):
    valori = ((tempo(riga), 'Tempo di slicer' if not mini else 'Tempo'),
              (grammi(totale(riga)), 'Materiale totale' if not mini else 'Totale'),
              (grammi(riga.get('supporti_g')), 'Di cui supporti' if not mini else 'Supporti'))
    st.html('<div class="r-metriche">' + ''.join(
        f'<div><b>{escape(valore)}</b><span>{etichetta}</span></div>'
        for valore, etichetta in valori) + '</div>')


def configurazioni_disponibili(dati, opt):
    righe = [r for r in opt.get('risultati', []) if riga_valida(r)]
    # Il profilo di riferimento è già sezionato anche per gli orientamenti
    # esclusi dalla ricerca delle varianti: non occorre inventare misure.
    riferimenti = [v for v in opt.get('varianti', []) if v.get('riferimento')]
    presenti = {(r['orientamento_id'], r['variante_id']) for r in righe}
    for orientamento in dati['orientamenti']:
        if riferimenti and risultato_valido(orientamento.get('slicer') or {}):
            extra = ottimizzazione.costruisci([orientamento], riferimenti, [], '')
            for r in extra['risultati']:
                if riga_valida(r) and (r['orientamento_id'], r['variante_id']) not in presenti:
                    righe.append(r)
    return {(r['orientamento_id'], r['variante_id']): r for r in righe}


def selezione_grafico(grafico_key, chiave, widget, oid):
    selezione = st.session_state[grafico_key]['selection'].get('profilo', [])
    if isinstance(selezione, list) and selezione:
        variante = selezione[-1].get('variante_id')
        if variante:
            st.session_state[chiave] = (oid, variante)
            st.session_state[widget] = (oid, variante)


def grafico(righe, scelta, chiave, widget, cartella, oid):
    if not righe:
        st.info('Non ci sono misure disponibili per questo orientamento.')
        return
    xs, ys = [totale(r) for r in righe], [r['tempo_s'] / 60 for r in righe]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    dx, dy = max(xmax - xmin, 1), max(ymax - ymin, 1)
    xmin, xmax = max(0, xmin - dx * .18), xmax + dx * .18
    ymin, ymax = max(0, ymin - dy * .25), ymax + dy * .25
    dati_grafico, etichette = [], []
    ordinate = sorted(righe, key=lambda r: (r['orientamento_id'], r['variante_id']) != scelta)
    for r in ordinate:
        xx = (totale(r) - xmin) / (xmax - xmin) * 520
        yy = (r['tempo_s'] / 60 - ymin) / (ymax - ymin) * 300
        selezionata = (r['orientamento_id'], r['variante_id']) == scelta
        nome = testo_profilo(r['variante'])
        label, lx, ly = '', totale(r), r['tempo_s'] / 60
        if selezionata or r['variante_id'] in {'bilanciato', 'dettaglio', 'robusto', 'veloce', 'economico'}:
            larghezza = min(180, len(nome) * 6)
            for ox, oy in ((10, 17), (10, -24), (-100, 24), (-100, -30), (-70, 50), (-100, -55)):
                ex = max(0, min(520 - larghezza, xx + ox))
                ey = max(12, min(290, yy + oy))
                rettangolo = (ex, ey - 8, ex + larghezza, ey + 8)
                if not any(not (rettangolo[2] < a or rettangolo[0] > c or rettangolo[3] < b or rettangolo[1] > d)
                           for a, b, c, d in etichette):
                    etichette.append(rettangolo)
                    label = nome
                    lx = xmin + ex / 520 * (xmax - xmin)
                    ly = ymin + ey / 300 * (ymax - ymin)
                    break
        frontiera = not any(totale(a) <= totale(r) and a['tempo_s'] <= r['tempo_s'] and
                             (totale(a) < totale(r) or a['tempo_s'] < r['tempo_s']) for a in righe)
        dati_grafico.append(dict(variante_id=r['variante_id'], nome=nome, totale=totale(r),
                                 minuti=r['tempo_s'] / 60, selezionata=selezionata,
                                 frontiera=frontiera, label=label, label_x=lx, label_y=ly))
    x = {'field': 'totale', 'type': 'quantitative', 'title': 'Materiale totale (g)',
         'scale': {'domain': [xmin, xmax], 'zero': False}, 'axis': {'grid': False, 'tickCount': 5, 'titleAnchor': 'end'}}
    y = {'field': 'minuti', 'type': 'quantitative', 'title': 'Tempo di slicer (min)',
         'scale': {'domain': [ymin, ymax], 'zero': False}, 'axis': {'tickCount': 5, 'titleAngle': 0, 'titleAlign': 'left', 'titleX': 0, 'titleY': -20}}
    spec = {
        'data': {'values': dati_grafico}, 'height': 420,
        'layer': [
            {'transform': [{'filter': 'datum.frontiera'}],
             'mark': {'type': 'line', 'strokeDash': [5, 5], 'color': '#e8772b'},
             'encoding': {'x': x, 'y': y, 'order': {'field': 'totale'}}},
            {'params': [{'name': 'profilo', 'select': {'type': 'point', 'fields': ['variante_id'],
                                                     'toggle': False, 'nearest': True, 'clear': False}}],
             'mark': {'type': 'point', 'filled': True, 'size': 145, 'strokeWidth': 2, 'cursor': 'pointer', 'opacity': 1},
             'encoding': {'x': x, 'y': y,
                          'fill': {'condition': {'test': 'datum.selezionata', 'value': '#e8772b'}, 'value': '#f7f7f4'},
                          'stroke': {'condition': {'test': 'datum.selezionata', 'value': '#e8772b'}, 'value': '#191b1b'},
                          'tooltip': [{'field': 'nome', 'title': 'Variante'}, {'field': 'minuti', 'title': 'Minuti', 'format': '.1f'},
                                      {'field': 'totale', 'title': 'Totale g', 'format': '.1f'}]}},
            {'transform': [{'filter': "datum.label !== ''"}],
             'mark': {'type': 'text', 'align': 'left', 'fontSize': 12, 'color': '#191b1b'},
             'encoding': {'x': {**x, 'field': 'label_x'},
                          'y': {**y, 'field': 'label_y'},
                          'text': {'field': 'label'}}}],
        'config': {'background': '#f7f7f4', 'view': {'stroke': None},
                   'axis': {'labelColor': '#686d6a', 'titleColor': '#686d6a', 'gridColor': '#d4d6d0',
                            'domain': False, 'ticks': False, 'labelFontSize': 12, 'titleFontWeight': 'normal',
                            'titlePadding': 22, 'labelPadding': 12}},
    }
    grafico_key = f'grafico_varianti_{cartella.name}_{oid}'
    st.vega_lite_chart(spec=spec, key=grafico_key, width='stretch', theme=None,
                       alt='Confronto tra tempo e materiale: seleziona un punto per cambiare profilo.',
                       on_select=lambda: selezione_grafico(grafico_key, chiave, widget, oid))
    st.caption('Punto arancione: configurazione selezionata. Linea tratteggiata: frontiera di Pareto per tempo e consumo totale.')
    st.caption('Seleziona un punto o usa la tabella. Qualità e resistenza restano indicatori separati.')


def mostra(cartella, dati, richiesta, slicer, percorso, *, download, bobina, controlli, consiglio, ricalcola):
    meccanica = confronto.meccanica(dati, richiesta)
    opt = ottimizzazione.aggiorna_priorita(dati.get('ottimizzazione_processo', {}),
                                         richiesta.get('priorita'), meccanica)
    attuale = bool(percorso and slicer and opt.get('firma') == confronto.firma(percorso, dati, richiesta))
    rac = opt.get('raccomandazione') if attuale else None
    esportabile = attuale and rac is not None
    configurazioni = configurazioni_disponibili(dati, opt)
    rac_chiave = (rac['orientamento_id'], rac['variante_id']) if rac else None
    chiave = f"esportazione_scelta_{cartella}_{opt.get('firma', '')}"
    widget = 'widget_' + chiave
    navigazione = f'risultati_schede_{cartella.name}'
    selezionata = st.session_state.get(chiave, rac_chiave)
    if selezionata not in configurazioni:
        selezionata = rac_chiave if rac_chiave in configurazioni else next(iter(configurazioni), None)
    st.session_state[chiave] = selezionata
    riga = configurazioni.get(selezionata)
    oid = riga['orientamento_id'] if riga else dati['orientamenti'][0]['id']
    orientamento = next(o for o in dati['orientamenti'] if o['id'] == oid)
    filamento = dati.get('sezionamento', {}).get('filamento', '')
    materiale = calibrazione.materiale_da_profilo(filamento, config.FILAMENTI) or filamento
    valutazione = stampabilita.valuta({**dati, 'orientamenti': [orientamento]}, config.VOLUME_STAMPA, config.UGELLO_MM)
    problemi = valutazione['controlli']

    with st.container(key='risultati_testata'):
        titolo, stato, azioni = st.columns([5, 1.4, 1])
        with titolo:
            st.html(f'<div class="strato-eyebrow">PROGETTO / {escape(cartella.name.split("_")[0])}</div><h1 class="r-titolo">{escape(Path(dati.get("file", cartella.name)).name)} <span>/ {escape(materiale)}</span></h1>')
        with azioni:
            st.button('＋ Nuovo pezzo', on_click=nuovo_pezzo, width='stretch')
        stato.caption(f"{len(dati['orientamenti'])} orientamenti analizzati")

    with st.container(key='risultati_pagine'):
        principale, orientamenti, varianti, verifiche, apprendimento = st.tabs(
            ['Risultato', 'Orientamenti', 'Varianti', 'Controlli', 'Consiglio e apprendimento'],
            key=navigazione, on_change='rerun')

        with principale:
            with st.container(key='risultato_schermata'):
                with st.container(key='risultato_hero', border=True):
                    scena, verdetto = st.columns([1.12, 1], gap=None)
                    with scena:
                        with st.container(key='risultato_stage'):
                            st.html(f'<div class="strato-eyebrow">ORIENTAMENTO {oid:02}</div><span class="r-numero">{oid:02}</span>')
                            modello(percorso, orientamento, interattivo=True)
                            st.html(f'<div class="strato-eyebrow">{escape(nome_orientamento(orientamento))}</div>')
                            st.caption('Supporti geometrici: rosso piatto · arancio pezzo · viola cavità')
                            st.button(f"Confronta i {len(dati['orientamenti'])} orientamenti ↗",
                                      key='apri_orientamenti', on_click=scheda, args=(navigazione, 'Orientamenti'))
                    with verdetto:
                        with st.container(key='risultato_verdetto'):
                            badge(bool(riga and attuale), 'ELEGOOSLICER · LOCALE' if attuale else 'CONFRONTO DA VERIFICARE')
                            titolo = ('Prima risolvi<br>i controlli.' if any(p['gravita'] == 'errore' for p in problemi)
                                      else 'Un buon punto<br>di partenza.' if rac and selezionata == rac_chiave
                                      else 'La tua<br>configurazione.' if rac else 'Una scelta<br>da verificare.')
                            st.html(f'<h2 class="r-verdetto">{titolo.replace("<br>", "<br> ")}</h2>')
                            st.caption((rac['motivo'].capitalize() + '.') if rac and selezionata == rac_chiave else
                                       'Confronta questa configurazione con il consiglio iniziale prima della stampa.')
                            st.divider()
                            selezione, cambia = st.columns([3, 1])
                            selezione.html(f'<div class="strato-eyebrow">CONFIGURAZIONE {"CONSIGLIATA" if selezionata == rac_chiave else "SELEZIONATA"}</div><strong>{escape(nome_orientamento(orientamento))} · {escape(testo_profilo(riga["variante"]) if riga else "Geometria")}</strong>')
                            cambia.button('Cambia ↗', on_click=scheda, args=(navigazione, 'Varianti'))
                            metriche(riga or orientamento.get('slicer') or {})
                            if esportabile and riga:
                                if meccanica and richiesta.get('priorita') == 'robustezza e rigidità' and (
                                        oid != meccanica['orientamento_consigliato'] or
                                        int(riga['wall_loops']) < meccanica['pareti_consigliate']):
                                    st.warning('La scelta manuale non rispetta orientamento o pareti suggeriti dal carico dichiarato.')
                                with st.container(key='risultato_download'):
                                    download(opt, riga)
                            else:
                                st.warning('Verifica il confronto con i profili e i carichi attuali per abilitare i download.')
                                if slicer:
                                    st.button('Calcola e verifica i processi', key='verifica_hero',
                                              on_click=lavorazioni.avvia, args=(cartella, 'varianti'))

                sinistra, destra = st.columns([1.12, 1], gap='medium')
                with sinistra:
                    with st.container(key='prima_stampa', border=True):
                        nome, link = st.columns([3, 1])
                        nome.markdown('**Prima di stampare**')
                        link.button('Tutti i controlli ↗', on_click=scheda, args=(navigazione, 'Controlli'))
                        for problema in problemi[:2]:
                            st.html(f'<div class="r-avviso"><strong>{escape(problema["controllo"])}</strong><p>{escape(problema["messaggio"])}</p><small>{escape(problema["azione"])}</small></div>')
                        if not problemi:
                            st.caption('Nessun problema rilevato dai controlli disponibili.')
                        if riga and esportabile:
                            bobina(riga)
                with destra:
                    with st.container(key='secondo_parere', border=True):
                        st.html('<div class="r-ai-copy"><h3>Un secondo parere, con il perché.</h3>'
                                '<p>La geometria dà i numeri. L’assistente AI scelto nelle Impostazioni può aiutarti a interpretarli, valutare i rischi e scegliere una prova utile.</p>'
                                '<small>Nessun invio automatico. La stampa non dipende dall’AI.</small></div>')
                        st.button('Chiedi un consiglio ↗', type='primary', on_click=chiedi_consiglio,
                                  args=(navigazione,))

        with orientamenti:
            st.subheader(f"Stesso pezzo. {len(dati['orientamenti'])} modi di appoggiarlo.")
            st.caption('Confronto degli orientamenti sezionati. La selezione aggiorna la configurazione da esportare.')
            for inizio in range(0, len(dati['orientamenti']), 3):
                colonne = st.columns(3, gap='medium')
                for colonna, o in zip(colonne, dati['orientamenti'][inizio:inizio + 3]):
                    with colonna:
                        with st.container(key=f"orientamento_card_{o['id']}", border=True):
                            with st.container(key=f"orientamento_thumb_{o['id']}"):
                                st.html(f'<span class="r-badge {"selezionata" if o["id"] == oid else ""}">{o["id"]:02}{" · Selezionato" if o["id"] == oid else ""}{" · Consigliato" if rac and o["id"] == rac["orientamento_id"] else ""}</span>')
                                modello(percorso, o)
                            s = o.get('slicer') or {}
                            titolo_card, misura_card = st.columns([3, 1])
                            titolo_card.markdown(f"**{nome_orientamento(o)}**")
                            with misura_card:
                                badge(risultato_valido(s))
                            st.html(f'<p class="r-card-desc">{escape(descrizione_orientamento(o))}</p>')
                            metriche(s, mini=True)
                            st.caption(f"Ribaltamento: {'Alto' if o.get('si_ribalta') else 'Basso'} · ◇ Euristico")
                            possibili = [k for k in configurazioni if k[0] == o['id']]
                            preferita = next((k for k in possibili if riga and k[1] == riga['variante_id']),
                                             possibili[0] if possibili else None)
                            st.button('✓ Selezionato' if o['id'] == oid else 'Scegli questo orientamento',
                                      key=f"scegli_orientamento_{o['id']}", width='stretch',
                                      type='primary' if o['id'] == oid else 'secondary', disabled=preferita is None,
                                      on_click=scegli, args=(chiave, widget, preferita, navigazione))
            with st.expander('Tabella completa degli orientamenti'):
                st.dataframe(pd.DataFrame([{k: v for k, v in o.items() if k not in ('trasformazione', 'slicer')}
                                          for o in dati['orientamenti']]), hide_index=True)

        with varianti:
            st.subheader('Trova il tuo compromesso.')
            st.caption(f'Grafico riferito all’orientamento {oid:02}. Il risultato applica il profilo all’orientamento selezionato.')
            righe = [r for r in configurazioni.values() if r['orientamento_id'] == oid]
            graf, profilo = st.columns([1.3, 1], gap='medium')
            with graf:
                with st.container(key='varianti_grafico', border=True):
                    grafico(righe, selezionata, chiave, widget, cartella, oid)
            with profilo:
                with st.container(key='variante_profilo', border=True):
                    st.html('<div class="strato-eyebrow">PROFILO SELEZIONATO</div>')
                    if riga:
                        st.header(testo_profilo(riga['variante']))
                        st.caption(testo_profilo(riga.get('descrizione', 'Configurazione misurata sul modello.')))
                        metriche(riga)
                        st.table(pd.DataFrame([
                            ('Altezza layer', f"{riga['layer_height']} mm"),
                            ('Pareti', str(riga['wall_loops'])),
                            ('Riempimento', str(riga['sparse_infill_density'])),
                            ('Supporti', grammi(riga.get('supporti_g'))),
                        ], columns=['Impostazione', 'Valore']).set_index('Impostazione'))
                        st.button(f"Usa {testo_profilo(riga['variante'])} e torna al risultato →", type='primary',
                                  width='stretch', on_click=scheda, args=(navigazione, 'Risultato'))
                    else:
                        st.info('Calcola i processi per confrontare i profili sul modello.')
            with st.container(key='varianti_tabella', border=True):
                id_riferimenti = {v['id'] for v in opt.get('varianti', []) if v.get('riferimento')}
                riferimento = next((r for r in righe if r['variante_id'] in id_riferimenti), {})
                colonne = st.columns([2, 1.4, 1, 1, 1, 1, 1])
                for colonna, etichetta in zip(colonne, ('Variante', 'Tempo', 'Totale', 'Supporti', 'Δ tempo', 'Δ materiale', '')):
                    colonna.caption(etichetta)
                for r in righe:
                    with st.container(key=f"variante_riga_{r['variante_id']}"):
                        colonne = st.columns([2, 1.4, 1, 1, 1, 1, 1])
                        valori = (testo_profilo(r['variante']), tempo(r), grammi(totale(r)), grammi(r.get('supporti_g')),
                                  delta(r.get('tempo_s'), riferimento.get('tempo_s')), delta(totale(r), totale(riferimento)))
                        for colonna, valore in zip(colonne, valori):
                            colonna.write(valore)
                        colonne[-1].button('Selezionato' if selezionata == (oid, r['variante_id']) else 'Scegli',
                                           key=f"scegli_variante_{r['variante_id']}",
                                           on_click=scegli, args=(chiave, widget, (oid, r['variante_id']), navigazione, 'Varianti'))
            ricalcola(opt)
            if esportabile and riga:
                with st.expander('Seleziona una configurazione da esportare'):
                    chiavi = list(configurazioni)
                    def descrivi(k):
                        r = configurazioni[k]
                        return f"Orientamento {k[0]} · {testo_profilo(r['variante'])} · layer {r['layer_height']} mm · {r['wall_loops']} pareti"
                    if st.session_state.get(widget) not in configurazioni:
                        st.session_state[widget] = selezionata
                    scelta_menu = st.selectbox('Configurazione da esportare', chiavi, format_func=descrivi, key=widget)
                    if scelta_menu != selezionata:
                        st.session_state[chiave] = scelta_menu
                        st.rerun()

        with verifiche:
            controlli()
        with apprendimento:
            consiglio()
