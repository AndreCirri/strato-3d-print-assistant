"""Controlli del G-code estruso e degli spostamenti, senza comandare la stampante."""
import math
import re
from pathlib import Path
from collections import defaultdict

import numpy as np


def analizza(percorso, larghezza=.45, massimo_segmenti=300000, avanzamento=None):
    pos = np.zeros(3)
    e = 0.
    relativo_e = False
    relativo_xyz = False
    tipo = 'Altro'
    passo = max(.2, larghezza)
    altezza = {}
    strati = defaultdict(set)
    collisioni = []
    supporti = []
    modello_min = np.array([np.inf, np.inf])
    modello_max = -modello_min.copy()
    conteggio = 0
    archi_non_letti = 0
    limitato = False
    dimensione = max(1, Path(percorso).stat().st_size)
    letti = 0
    with open(percorso, encoding='utf-8', errors='replace') as f:
        for numero_riga, riga in enumerate(f):
            letti += len(riga.encode('utf-8'))
            if avanzamento and numero_riga % 2000 == 0:
                avanzamento(.75 * min(1., letti / dimensione), 'Lettura dei percorsi G-code')
            if riga.startswith(';TYPE:'):
                tipo = riga[6:].strip()
            codice = riga.split(';')[0].strip().split()
            if not codice:
                continue
            comando = codice[0]
            param = {k: float(v) for k, v in re.findall(r'([XYZEFIJK])(-?[\d.]+)', ' '.join(codice[1:]))}
            if comando == 'M83': relativo_e = True
            elif comando == 'M82': relativo_e = False
            elif comando == 'G91': relativo_xyz = True
            elif comando == 'G90': relativo_xyz = False
            elif comando == 'G92':
                if 'E' in param: e = param['E']
                for i, k in enumerate('XYZ'):
                    if k in param: pos[i] = param[k]
            elif comando in ('G0', 'G1', 'G2', 'G3'):
                nuovo = pos.copy()
                for i, k in enumerate('XYZ'):
                    if k in param: nuovo[i] = pos[i] + param[k] if relativo_xyz else param[k]
                estruso = (param.get('E', 0) if relativo_e else param.get('E', e) - e)
                if 'E' in param: e = e + param['E'] if relativo_e else param['E']
                if np.linalg.norm(nuovo[:2] - pos[:2]) < 1e-8 and comando not in ('G2', 'G3'):
                    pos = nuovo
                    continue
                conteggio += 1
                if conteggio > massimo_segmenti:
                    limitato = True
                    break
                n = max(2, int(np.ceil(np.linalg.norm(nuovo[:2] - pos[:2]) / passo)) + 1)
                if comando in ('G2', 'G3'):
                    if not ('I' in param or 'J' in param):
                        archi_non_letti += 1
                        pos = nuovo
                        continue
                    centro = pos[:2] + [param.get('I', 0), param.get('J', 0)]
                    raggio = np.linalg.norm(pos[:2] - centro)
                    a0 = math.atan2(*(pos[:2] - centro)[::-1])
                    a1 = math.atan2(*(nuovo[:2] - centro)[::-1])
                    delta = (a1 - a0) % (2 * math.pi)
                    if comando == 'G2': delta = -((a0 - a1) % (2 * math.pi))
                    if abs(delta) < 1e-8: delta = 2 * math.pi * (-1 if comando == 'G2' else 1)
                    n = max(2, int(abs(delta) * raggio / passo) + 1)
                    angoli = np.linspace(a0, a0 + delta, min(n, 10000))
                    punti = np.column_stack((centro[0] + raggio * np.cos(angoli),
                                             centro[1] + raggio * np.sin(angoli),
                                             np.linspace(pos[2], nuovo[2], len(angoli))))
                else:
                    punti = np.linspace(pos, nuovo, min(n, 10000))
                celle = {(int(round(p[0] / passo)), int(round(p[1] / passo))): float(p[2]) for p in punti}
                if estruso > 1e-7:
                    for cella, z in celle.items(): altezza[cella] = max(z, altezza.get(cella, -np.inf))
                    if tipo not in ('Custom', 'Skirt', 'Brim', 'Altro'):
                        strati[round(float(nuovo[2]), 3)].update(celle)
                        if 'Support' in tipo:
                            if conteggio % 5 == 0 and len(supporti) < 20000:
                                supporti.append(((pos + nuovo) / 2).tolist())
                        else:
                            modello_min = np.minimum(modello_min, punti[:, :2].min(axis=0))
                            modello_max = np.maximum(modello_max, punti[:, :2].max(axis=0))
                else:
                    attraversa = [(c, z, altezza[c]) for c, z in celle.items()
                                   if c in altezza and altezza[c] > z + .05]
                    if attraversa and len(collisioni) < 100:
                        c, z, h = attraversa[0]
                        collisioni.append({'x_mm': c[0] * passo, 'y_mm': c[1] * passo,
                                           'z_mm': round(z, 3), 'materiale_gia_stampato_z_mm': round(h, 3)})
                pos = nuovo
    # Componenti connesse dei percorsi depositati: cerca inizi senza materiale sotto.
    sotto = {}
    isole = []
    discontinuita = []
    for indice_strato, (z, celle) in enumerate(sorted(strati.items())):
        if avanzamento:
            avanzamento(.75 + .25 * indice_strato / max(1,len(strati)),
                         f'Controllo appoggi del toolpath — strato {indice_strato+1} di {len(strati)}')
        restanti = set(celle)
        componenti = []
        while restanti:
            seme = restanti.pop()
            componente = {seme}
            pila = [seme]
            while pila:
                x, y = pila.pop()
                for vicino in ((x+1,y),(x-1,y),(x,y+1),(x,y-1),(x+1,y+1),(x-1,y-1),(x-1,y+1),(x+1,y-1)):
                    if vicino in restanti:
                        restanti.remove(vicino)
                        componente.add(vicino)
                        pila.append(vicino)
            componenti.append(componente)
        if len(componenti) > 1:
            discontinuita.append({'z_mm': z, 'regioni_separate': len(componenti)})
        if sotto:
            for comp in componenti:
                appoggiata = any((x+dx,y+dy) in sotto and 0 < z - sotto[(x+dx,y+dy)] <= .5
                                 for x,y in comp for dx,dy in ((0,0),(1,0),(-1,0),(0,1),(0,-1)))
                if not appoggiata:
                    x, y = next(iter(comp))
                    isole.append({'z_mm': z, 'x_mm': x*passo, 'y_mm': y*passo, 'celle': len(comp)})
        sotto.update({c: z for c in celle})
    if avanzamento:
        avanzamento(1., 'Controllo toolpath completato')
    return {'segmenti_letti': conteggio, 'campionamento_mm': passo, 'limitato': limitato,
            'archi_non_analizzati': archi_non_letti, 'collisioni': collisioni,
            'isole_senza_appoggio': isole[:100], 'percorsi_disconnessi': discontinuita[:100],
            'punti_supporto': supporti, 'centro_modello_xy': ((modello_min + modello_max)/2).tolist()
            if np.isfinite(modello_min).all() else None,
            'limite': 'Controllo campionato dei percorsi: non include ingombro della testina, deformazioni, tolleranze o urti alla stessa quota.'}
