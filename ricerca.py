"""Ricerca locale progressiva: una modifica alla volta, con budget esplicito."""
from copy import deepcopy

from persistenza import impronta
from validazione import riga_valida
import ottimizzazione

VERSIONE = 1
LIMITI = {"layer_height": (.12, .28, .04), "wall_loops": (2, 5, 1),
          "sparse_infill_density": (5, 35, 5)}


def proponi(righe, varianti, priorita, meccanica=None):
    valide = [r for r in righe if riga_valida(r)]
    if meccanica and 'robustezza' in (priorita or ''):
        valide = [r for r in valide if r['orientamento_id'] == meccanica['orientamento_consigliato']
                  and int(r['wall_loops']) >= meccanica['pareti_consigliate']]
    if not valide:
        return None
    viste = {(r['orientamento_id'], tuple(str(r[k]) for k in LIMITI)) for r in righe}
    direzioni = [('layer_height', 1), ('sparse_infill_density', -1), ('wall_loops', -1)]
    if 'materiale' in (priorita or ''):
        direzioni = [('sparse_infill_density', -1), ('wall_loops', -1), ('layer_height', 1)]
    elif 'robustezza' in (priorita or ''):
        direzioni = [('wall_loops', 1), ('sparse_infill_density', 1), ('layer_height', -1)]
    elif any(x in (priorita or '') for x in ('superficie', 'precisione')):
        direzioni = [('layer_height', -1), ('wall_loops', 1), ('sparse_infill_density', -1)]
    # Esauriti i vicini del migliore, esplora i vicini degli altri risultati validi.
    while valide:
        scelta = ottimizzazione.scegli(valide, priorita)
        seme = next(r for r in valide if r['orientamento_id'] == scelta['orientamento_id']
                    and r['variante_id'] == scelta['variante_id'])
        impostazioni = {k: seme[k] for k in LIMITI}
        for campo, verso in direzioni + [(k, -s) for k, s in direzioni]:
            minimo, massimo, passo = LIMITI[campo]
            valore = float(str(seme[campo]).rstrip('%'))
            nuovo = round(valore + passo * verso, 2)
            if not minimo <= nuovo <= massimo:
                continue
            if campo == 'wall_loops' and meccanica and 'robustezza' in (priorita or ''):
                if nuovo < meccanica['pareti_consigliate']:
                    continue
            parametri = deepcopy(impostazioni)
            parametri[campo] = (f'{nuovo:g}%' if campo == 'sparse_infill_density' else f'{nuovo:g}')
            chiave = (seme['orientamento_id'], tuple(str(parametri[k]) for k in LIMITI))
            if chiave in viste:
                continue
            codice = 'ricerca_' + impronta(parametri)[:10]
            variante = {'id': codice, 'nome': f'Ricerca {campo} {parametri[campo]}',
                        'descrizione': f"Variazione singola da {seme['variante']}", 'impostazioni': parametri}
            return seme['orientamento_id'], variante
        valide.remove(seme)
    return None
