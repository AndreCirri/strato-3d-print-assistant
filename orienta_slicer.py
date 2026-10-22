"""Come orienterebbe il pezzo il pulsante "Orientamento automatico" dello slicer.

Traduzione in Python di OrcaSlicer (da cui deriva ElegooSlicer):
  src/libslic3r/Orient.cpp            AutoOrienter: candidati, get_features, target_function
  src/slic3r/GUI/Jobs/OrientJob.cpp   parametri della modalità predefinita "area minima dei supporti"
  src/slic3r/GUI/GLCanvas3D.hpp       OrientSettings.min_area = true
Codice originale: https://github.com/SoftFever/OrcaSlicer (licenza AGPL-3.0).

Differenze note dall'originale: le facce "di aspetto" (solo nei 3MF di Orca/Bambu) non sono
riconosciute, quindi non hanno la penalità extra; la rotazione attorno a Z per la ventola non
c'è (non cambia supporti né appoggio). Il risultato è quindi una stima della scelta dello slicer.
"""
import numpy as np
import trimesh

EPSILON = 1e-4                     # libslic3r.h
PARAMETRI = {
    # pulsante "Orienta automaticamente" dell'interfaccia: OrientSettings.min_area = true
    # -> setMinimalSupportAreaPrams() in OrientJob.cpp; angolo = soglia supporti del profilo
    "interfaccia": dict(RELATIVE_F=20.0, CONTOUR_F=0.5, BOTTOM_F=2.5, BOTTOM_HULL_F=0.1, TAR_C=0.1, TAR_D=1.0,
                        TAR_LAF=0.001, FIRST_LAY_H=0.2, LAF_MIN=0.97, LAF_MAX=0.999, BOTTOM_MIN=0.1),
    # riga di comando (--orient): valori predefiniti di OrientParams in Orient.hpp, angolo 60°
    "riga_di_comando": dict(RELATIVE_F=6.610621027964314, CONTOUR_F=0.23228623269775997, BOTTOM_F=1.167152017941474,
                            BOTTOM_HULL_F=0.1, TAR_C=0.24308070476924726, TAR_D=0.6284515508160871,
                            TAR_LAF=0.01, FIRST_LAY_H=0.2, LAF_MIN=0.9703, LAF_MAX=0.999, BOTTOM_MIN=0.1),
}
ANGOLO_RIGA_DI_COMANDO = 60.0
SUPPLEMENTI = np.array([
    [0, 0, -1], [0.70710678, 0, -0.70710678], [0, 0.70710678, -0.70710678],
    [-0.70710678, 0, -0.70710678], [0, -0.70710678, -0.70710678],
    [1, 0, 0], [0.70710678, 0.70710678, 0], [0, 1, 0], [-0.70710678, 0.70710678, 0],
    [-1, 0, 0], [-0.70710678, -0.70710678, 0], [0, -1, 0], [0.70710678, -0.70710678, 0],
    [0.70710678, 0, 0.70710678], [0, 0.70710678, 0.70710678],
    [-0.70710678, 0, 0.70710678], [0, -0.70710678, 0.70710678], [0, 0, 1]])


def _cumula(normali, aree, n):
    """area_cumulation_accurate: raggruppa le normali quantizzate a 0,001, somma le aree,
    tiene le n direzioni con più area (rappresentate dalla normale della faccia più grande)."""
    gruppi = {}
    for nrm, a in zip(normali, aree):
        k = tuple(np.floor(nrm * 1000) / 1000)
        tot, a_max, rappr = gruppi.get(k, (0.0, 0.0, nrm))
        gruppi[k] = (tot + a, a, nrm) if a > a_max else (tot + a, a_max, rappr)
    ordinati = sorted(gruppi.values(), key=lambda g: -g[0])
    return [g[2] for g in ordinati[:n]]


def candidati(mesh):
    lista = [np.array([0.0, 0.0, -1.0])]
    lista += _cumula(mesh.face_normals, mesh.area_faces, 10)
    scafo = mesh.convex_hull
    lista += _cumula(scafo.face_normals, scafo.area_faces, 14)
    lista += list(SUPPLEMENTI.astype(float))
    unici = []
    for c in lista:                                   # remove_duplicates
        if np.linalg.norm(c) < 1e-9 or any(np.allclose(c, u, atol=1e-7) for u in unici):
            continue
        unici.append(np.asarray(c, float))
    return unici


def costo(mesh, su, soglia_gradi=30.0, scafo=None, modo="interfaccia"):
    """get_features + target_function (min_volume = false) per la direzione 'su'
    (quella che finisce verso l'alto). Il termine TAR_PROJ_AREA*area_projected è sempre 0 in Orca."""
    p = PARAMETRI[modo]
    scafo = scafo if scafo is not None else mesh.convex_hull
    ascent = np.cos(np.pi - np.radians(soglia_gradi))
    z = mesh.triangles @ su                           # (facce, 3) quote dei vertici
    z_max, zmin = z.max(axis=1), z.min()
    aree = mesh.area_faces
    fondo1 = z_max < zmin + p["FIRST_LAY_H"] - EPSILON
    fondo2 = z_max < zmin + p["FIRST_LAY_H"] / 2 - EPSILON
    fondo = aree[fondo1].sum() * 0.5 + aree[fondo2].sum()
    proiez = mesh.face_normals @ su
    sporgenza = aree[(proiez < ascent) & ~fondo2].sum()
    contorno = 4 * np.sqrt(fondo)
    fondo_scafo = scafo.area_faces[(scafo.triangles @ su).max(axis=1) < zmin + p["FIRST_LAY_H"] - EPSILON].sum()
    pa = np.abs(proiez)
    laf = aree[(pa < p["LAF_MAX"]) & (pa > p["LAF_MIN"]) & (z_max > zmin + p["FIRST_LAY_H"])].sum()
    c = p["RELATIVE_F"] * (sporgenza * p["TAR_C"] + p["TAR_D"] + p["TAR_LAF"] * laf) / (
        p["TAR_D"] + p["CONTOUR_F"] * contorno + p["BOTTOM_F"] * fondo + p["BOTTOM_HULL_F"] * fondo_scafo)
    c += 100 * (fondo < p["BOTTOM_MIN"])
    return float(c), {"sporgenze_slicer_mm2": round(float(sporgenza), 1), "appoggio_slicer_mm2": round(float(fondo), 1),
                      "fondo_scafo_mm2": round(float(fondo_scafo), 1), "contorno": round(float(contorno), 1),
                      "facce_quasi_piane_mm2": round(float(laf), 1)}


def scelta_slicer(mesh, soglia_gradi=30.0, modo="interfaccia"):
    """Ritorna la direzione che lo slicer metterebbe in alto, la trasformazione e la classifica."""
    if modo == "riga_di_comando":
        soglia_gradi = ANGOLO_RIGA_DI_COMANDO
    scafo = mesh.convex_hull
    risultati = []
    for c in candidati(mesh):
        su = -c                                       # Orient.cpp: orientation = -orientations[i]
        val, dettagli = costo(mesh, su, soglia_gradi, scafo, modo)
        risultati.append((val, su, dettagli))
    risultati.sort(key=lambda r: r[0])
    migliore = risultati[0]
    z = np.array([0.0, 0.0, 1.0])
    # a parità di costo Orca preferisce non ribaltare il pezzo (su = +Z)
    if abs(migliore[1] @ z - 1) > EPSILON:
        for r in risultati[1:]:
            if abs(r[0] - migliore[0]) >= EPSILON:
                break
            if abs(r[1] @ z - 1) < EPSILON * EPSILON:
                migliore = r
                break
    T = trimesh.geometry.align_vectors(migliore[1], z)
    return {"modo": modo, "angolo_gradi": soglia_gradi,
            "su": migliore[1].round(4).tolist(), "costo": round(migliore[0], 3), "trasformazione": T.tolist(),
            "dettagli": migliore[2],
            "classifica": [{"su": r[1].round(3).tolist(), "costo": round(r[0], 3)} for r in risultati[:5]]}


def direzione_su(T):
    """Per una trasformazione già applicata al pezzo: quale direzione del file finisce in alto."""
    R = np.asarray(T)[:3, :3]
    return R.T @ np.array([0.0, 0.0, 1.0])
