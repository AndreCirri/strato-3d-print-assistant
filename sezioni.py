"""Controlli geometrici mediante sezioni orizzontali e connettività del volume libero."""
import math
import numpy as np
from shapely.geometry import Polygon, LineString, Point, box
from shapely.ops import polygonize, unary_union


def sezione_materiale(mesh, z):
    # Evita piani esattamente coincidenti con facce/vertici: l'interno sul bordo è ambiguo.
    z += 1e-5
    sezione = mesh.section(plane_origin=[0,0,z], plane_normal=[0,0,1])
    if sezione is None:
        return Polygon()
    poligoni = list(polygonize([LineString(p[:, :2]) for p in sezione.discrete]))
    if not poligoni:
        return Polygon()
    punti = [list(p.representative_point().coords[0]) + [z] for p in poligoni]
    dentro = mesh.contains(punti)
    return unary_union([p for p, valido in zip(poligoni, dentro) if valido])


def poligoni(geometria):
    if geometria.is_empty: return []
    if geometria.geom_type == 'Polygon': return [geometria]
    return [p for g in geometria.geoms for p in poligoni(g)]


def dimensioni(p):
    xy = np.asarray(p.minimum_rotated_rectangle.exterior.coords)[:4]
    lati = np.roll(xy, -1, axis=0) - xy
    lunghezze = np.linalg.norm(lati, axis=1)
    i = int(np.argmin(lunghezze))
    return float(lunghezze[i]), lati[i] / max(lunghezze[i], 1e-8)


def accessibilita(materiali, dominio, raggio=0):
    regioni, collegamenti, esterni = [], [], set()
    precedenti = []
    for livello, materiale in enumerate(materiali):
        libere = poligoni(dominio.difference(materiale).buffer(-raggio))
        attuali = []
        for area in libere:
            nodo = len(regioni)
            regioni.append((livello, area))
            collegamenti.append(set())
            attuali.append(nodo)
            if area.distance(dominio.boundary) <= raggio + 1e-5:
                esterni.add(nodo)
            for vecchio in precedenti:
                if regioni[vecchio][1].intersection(area).area > 1e-5:
                    collegamenti[nodo].add(vecchio)
                    collegamenti[vecchio].add(nodo)
        precedenti = attuali
    raggiunti = set(esterni)
    pila = list(esterni)
    while pila:
        for altro in collegamenti[pila.pop()]:
            if altro not in raggiunti:
                raggiunti.add(altro)
                pila.append(altro)
    chiusi = set(range(len(regioni))) - raggiunti
    gruppi = []
    while chiusi:
        seme = chiusi.pop()
        gruppo = [seme]
        pila = [seme]
        while pila:
            for altro in collegamenti[pila.pop()]:
                if altro in chiusi:
                    chiusi.remove(altro)
                    gruppo.append(altro)
                    pila.append(altro)
        gruppi.append(gruppo)
    return regioni, gruppi


def analizza(mesh, ugello=.4, massimo_sezioni=100, dati_toolpath=None, avanzamento=None):
    if not mesh.is_volume:
        return {'disponibile': False, 'motivo': 'Serve una geometria volumetrica affidabile'}
    passo = max(.4, float(mesh.extents[2]) / massimo_sezioni)
    quote = np.arange(mesh.bounds[0,2] - passo/2, mesh.bounds[1,2] + passo, passo)
    materiali = []
    for i, z in enumerate(quote):
        if avanzamento:
            avanzamento(.6 * i / len(quote), f'Sezioni geometriche — {i+1} di {len(quote)}')
        materiali.append(sezione_materiale(mesh, float(z)))
    dominio = box(*(mesh.bounds[0,:2] - 3), *(mesh.bounds[1,:2] + 3))
    if avanzamento: avanzamento(.6, 'Ricerca delle cavità chiuse')
    regioni, chiuse = accessibilita(materiali, dominio)
    if avanzamento: avanzamento(.7, 'Verifica accessibilità dei supporti')
    regioni_utensile, difficili = accessibilita(materiali, dominio, raggio=1.)
    cavita = []
    for gruppo in chiuse:
        volume = sum(regioni[i][1].area * passo for i in gruppo)
        if volume < 1: continue
        cavita.append({'volume_stimato_mm3': round(volume,1),
                       'z_min_mm': round(float(min(quote[regioni[i][0]] for i in gruppo)),2),
                       'z_max_mm': round(float(max(quote[regioni[i][0]] for i in gruppo)),2)})
    fori, ponti, isole = [], [], []
    visti_fori = set()
    iniziato = False
    for livello in range(1, len(materiali)):
        if avanzamento and livello % 5 == 0:
            avanzamento(.8 + .19 * livello / len(materiali), f'Controllo ponti e fori — sezione {livello} di {len(materiali)}')
        attuale, prima = materiali[livello], materiali[livello-1]
        for parte in poligoni(attuale):
            if iniziato and not parte.intersects(prima.buffer(passo / math.tan(math.radians(30)))):
                punto = parte.representative_point()
                isole.append({'z_mm': round(float(quote[livello]),2), 'area_mm2': round(parte.area,2),
                               'x_mm': round(punto.x,2), 'y_mm': round(punto.y,2)})
            for anello in parte.interiors:
                buco = Polygon(anello)
                diametro, _ = dimensioni(buco)
                centro = buco.centroid
                chiave = (round(centro.x), round(centro.y))
                if diametro < 4 * ugello and chiave not in visti_fori:
                    visti_fori.add(chiave)
                    fori.append({'larghezza_minima_mm': round(diametro,2),
                                 'x_mm': round(centro.x,2), 'y_mm': round(centro.y,2)})
        iniziato = iniziato or attuale.area > 0
        if prima.is_empty: continue
        nuovi = poligoni(attuale.difference(prima.buffer(ugello/2)))
        for nuovo in nuovi:
            if nuovo.area < ugello ** 2: continue
            _, direzione_minima = dimensioni(nuovo)
            centro = np.asarray(nuovo.centroid.coords[0])
            possibili = []
            for direzione in (direzione_minima, np.array([-direzione_minima[1], direzione_minima[0]])):
                proiezioni = np.asarray(nuovo.exterior.coords) @ direzione
                luce = float(proiezioni.max() - proiezioni.min())
                estremi = [Point(centro + s*direzione*(luce/2 + ugello)) for s in (-1,1)]
                if all(prima.buffer(ugello/4).covers(p) for p in estremi):
                    possibili.append((luce, direzione))
            if possibili:
                luce, direzione = min(possibili, key=lambda x: x[0])
                ponti.append({'z_mm': round(float(quote[livello]),2), 'luce_mm': round(luce+ugello,2),
                              'direzione_gradi': round(math.degrees(math.atan2(direzione[1],direzione[0])) % 180,1)})
    supporti_chiusi = 0
    if dati_toolpath and dati_toolpath.get('centro_modello_xy'):
        offset = np.array(dati_toolpath['centro_modello_xy']) - mesh.bounds[:,:2].mean(axis=0)
        nodi_chiusi = {n for g in chiuse for n in g}
        for x, y, z in dati_toolpath.get('punti_supporto', []):
            livello = int(np.argmin(abs(quote - z)))
            if any(regioni[n][0] == livello and regioni[n][1].covers(Point(np.array([x,y]) - offset))
                   for n in nodi_chiusi):
                supporti_chiusi += 1
    if avanzamento: avanzamento(1., 'Controlli geometrici completati')
    return {'disponibile': True, 'passo_sezioni_mm': round(passo,3), 'numero_sezioni': len(quote),
            'cavita_chiuse': cavita, 'zone_inaccessibili_utensile_2mm': len(difficili),
            'fori_piccoli': fori[:100], 'ponti': ponti[:100], 'isole_geometriche': isole[:100],
            'campioni_supporto_in_cavita_chiuse': supporti_chiusi,
            'limite': 'Controlli per sezioni campionate: aperture o dettagli più piccoli del passo possono sfuggire. '
                      'L’accessibilità riguarda un utensile di diametro 2 mm; i supporti sono allineati per centro del modello.'}
