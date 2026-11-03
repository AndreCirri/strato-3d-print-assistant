"""Collega i controlli geometrici al G-code della configurazione selezionata."""
import hashlib
import config
import sezioni
import toolpath
from persistenza import impronta, impronta_file


def calcola(cartella, dati, mesh, avanzamento=None):
    rac = dati.get('ottimizzazione_processo', {}).get('raccomandazione')
    oid = rac['orientamento_id'] if rac else dati['orientamenti'][0]['id']
    orientamento = next(o for o in dati['orientamenti'] if o['id'] == oid)
    m = mesh.copy()
    m.apply_transform(orientamento['trasformazione'])
    m.apply_translation(-m.bounds[0])
    sotto = cartella / 'sezionamenti' / f'orientamento_{oid}'
    if rac:
        variante = next(v for v in dati['ottimizzazione_processo']['varianti'] if v['id'] == rac['variante_id'])
        if not variante.get('riferimento'):
            sotto = cartella / 'varianti' / f'orientamento_{oid}' / variante['id']
    file = sorted(sotto.glob('*.gcode'))
    firma = impronta({'mesh': hashlib.sha256(m.vertices.tobytes()+m.faces.tobytes()).hexdigest(),
                     'gcode': impronta_file(file[0]) if file else None, 'ugello': config.UGELLO_MM, 'versione': 1})
    if dati.get('controlli_dettagliati', {}).get('firma') == firma:
        if avanzamento: avanzamento(1., 'Controlli già verificati')
        return
    percorso = toolpath.analizza(file[0], larghezza=config.UGELLO_MM * 1.1,
        avanzamento=(lambda f, fase: avanzamento(.5*f, fase)) if avanzamento else None) if file else None
    geometria = sezioni.analizza(m, config.UGELLO_MM, dati_toolpath=percorso,
        avanzamento=(lambda f, fase: avanzamento(.5+.5*f, fase)) if avanzamento else None)
    if avanzamento: avanzamento(1., 'Controlli dettagliati completati')
    if percorso:
        percorso.pop('punti_supporto', None)
    dati['controlli_dettagliati'] = {'firma': firma, 'orientamento_id': oid,
                                    'variante': rac['variante_id'] if rac else 'bilanciato',
                                    'geometria': geometria, 'toolpath': percorso}
