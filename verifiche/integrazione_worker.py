import json
import tempfile
import time
import sys
import zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import trimesh
from streamlit.testing.v1 import AppTest
import config
import confronto
import lavorazioni
import slicer_cli
from persistenza import salva_json, impronta_file


def attendi(p):
    limite = time.monotonic() + 180
    while time.monotonic() < limite:
        stato = lavorazioni.stato(p)
        if stato.get('stato') != 'in corso':
            if stato.get('stato') != 'completata':
                print((p/'lavorazione.log').read_text(encoding='utf-8')[-6000:], flush=True)
                raise AssertionError(stato)
            while lavorazioni.vivo(stato.get('pid')) and time.monotonic() < limite:
                time.sleep(.1)
            return
        time.sleep(.5)
    raise AssertionError('Timeout worker')


with tempfile.TemporaryDirectory(prefix='assistente_integrazione_') as tmp:
    root = Path(tmp)
    p = root / 'lavoro'
    p.mkdir()
    trimesh.creation.box(extents=[10, 8, 6]).export(p / 'pezzo.stl')
    richiesta = {'profilo_filamento': config.PROFILO_FILAMENTO, 'priorita': 'velocità di stampa',
                 'scopo': 'Prova persistenza', 'direzione_carico': 'non specificata',
                 'sollecitazione': 'non specificata'}
    salva_json(p / 'richiesta.json', richiesta)
    salva_json(p / 'ingresso.json', {'file': 'pezzo.stl', 'sha256': impronta_file(p / 'pezzo.stl')})
    lavorazioni.avvia(p)
    print('Worker avviato', flush=True)
    # Una nuova istanza della dashboard non deve interrompere il calcolo né bloccare le altre schede.
    precedente = config.LAVORI
    config.LAVORI = root
    try:
        app = AppTest.from_file(str(config.CARTELLA / 'app.py'), default_timeout=30)
        app.query_params['lavoro'] = p.name
        app.run()
        assert not app.exception, [e.message for e in app.exception]
        assert len(app.tabs) == 4
        if lavorazioni.stato(p).get('stato') == 'in corso':
            assert app.get('progress'), 'Barra di avanzamento assente'
        print('Dashboard e schede disponibili durante il calcolo', flush=True)
        attendi(p)
        dati = json.loads((p / 'analisi.json').read_text(encoding='utf-8'))
        opt = dati['ottimizzazione_processo']
        assert opt['raccomandazione']
        assert not [r for r in opt['risultati'] if r.get('errore')]
        prima = {str(f): f.stat().st_mtime_ns for f in p.rglob('*.gcode')}
        print('Analisi completa:', len(opt['risultati']), 'righe valide', flush=True)
        # Ripresa: deve riusare i G-code, non eseguire nuovi sezionamenti.
        lavorazioni.avvia(p, 'varianti')
        attendi(p)
        dopo = {str(f): f.stat().st_mtime_ns for f in p.rglob('*.gcode')}
        assert prima == dopo
        print('Ripresa senza nuovi sezionamenti', flush=True)
        app.run()
        assert not app.exception, [e.message for e in app.exception]
        assert any('Scarica profilo' in x.label for x in app.get('download_button'))
        app.text_area(key='scopo').set_value('Modifica persistita senza Claude').run()
        assert json.loads((p / 'richiesta.json').read_text(encoding='utf-8'))['scopo'] == 'Modifica persistita senza Claude'
        print('Persistenza richiesta e download verificati', flush=True)
        app2 = AppTest.from_file(str(config.CARTELLA / 'app.py'), default_timeout=30)
        app2.query_params['lavoro'] = p.name
        app2.run()
        assert app2.text_area(key='scopo').value == 'Modifica persistita senza Claude'
        print('Riapertura ripristina la richiesta', flush=True)
        # Calcolo meccanico reale, anche fuori dai due orientamenti iniziali.
        app2.selectbox(key='priorita').select('robustezza e rigidità')
        app2.selectbox(key='sollecitazione').select('trazione')
        app2.selectbox(key='direzione_carico').select('asse Z del file')
        app2.selectbox(key='parte_critica').select('gancio').run()
        assert not app2.exception
        assert not app2.get('download_button')  # nessun download di un profilo incompatibile col carico
        richiesta = json.loads((p / 'richiesta.json').read_text(encoding='utf-8'))
        lavorazioni.avvia(p, 'varianti')
        attendi(p)
        dati = json.loads((p / 'analisi.json').read_text(encoding='utf-8'))
        rac = dati['ottimizzazione_processo']['raccomandazione']
        scelta = next(r for r in dati['ottimizzazione_processo']['risultati']
                      if r['orientamento_id'] == rac['orientamento_id'] and r['variante_id'] == rac['variante_id'])
        assert int(scelta['wall_loops']) >= 5
        app2.run()
        assert not app2.exception
        next(b for b in app2.button if b.label == 'Prepara progetto 3MF').click().run()
        attendi(p)
        app2.run()
        assert not app2.exception
        assert any(b.label == 'Scarica progetto 3MF' for b in app2.get('download_button'))
        progetto = next((p / 'esportazioni').glob('*.3mf'))
        with zipfile.ZipFile(progetto) as archivio:
            settings = json.loads(archivio.read('Metadata/project_settings.config'))
            assert str(settings['wall_loops']) == '5', settings.get('wall_loops')
        print('Profilo meccanico e 3MF verificati end to end', flush=True)
    finally:
        config.LAVORI = precedente
        fine = time.monotonic() + 180
        while (lavorazioni.stato(p).get('stato') == 'in corso'
               or lavorazioni.vivo(lavorazioni.stato(p).get('pid'))) and time.monotonic() < fine:
            time.sleep(.5)
