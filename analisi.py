"""Analisi geometrica di un STL per la stampa FDM. Solo calcoli: nessuna AI qui.

Tutte le misure sono in mm. Gli orientamenti candidati sono le pose stabili del pezzo
(le facce su cui può appoggiare sul piatto) calcolate da trimesh.
"""
import math
import warnings
from collections import Counter
import numpy as np
import trimesh

warnings.filterwarnings("ignore", category=RuntimeWarning, module="trimesh")

MAX_RAGGI = 20000          # facce campionate per i calcoli con i raggi (pezzi grandi)
SOGLIA_SUPPORTI = 30.0     # gradi rispetto all'orizzontale, come "Angolo di soglia" dello slicer
DENSITA = {"PLA": 1.24, "PETG": 1.27, "ASA": 1.07, "ABS": 1.04, "TPU": 1.21, "PLA-CF": 1.29}


def carica(percorso):
    # validate=True scarta i triangoli degeneri (area zero), frequenti negli STL esportati
    mesh = trimesh.load_mesh(percorso, force="mesh", process=True, validate=True)
    trimesh.repair.fill_holes(mesh)
    trimesh.repair.fix_normals(mesh)
    return mesh


def bordi_aperti(mesh):
    uso = Counter(map(tuple, mesh.edges_sorted.tolist()))
    return sum(1 for k in uso.values() if k != 2)


def _campione(n, rng):
    idx = np.arange(n)
    return idx if n <= MAX_RAGGI else rng.choice(idx, MAX_RAGGI, replace=False)


def spessori(mesh, rng):
    """Spessore locale: raggio dalla faccia verso l'interno fino alla parete opposta."""
    idx = _campione(len(mesh.faces), rng)
    n = mesh.face_normals[idx]
    orig = mesh.triangles_center[idx] - n * 1e-3
    loc, iray, _ = mesh.ray.intersects_location(orig, -n, multiple_hits=False)
    d = np.full(len(idx), np.nan)
    d[iray] = np.linalg.norm(loc - orig[iray], axis=1)
    area = mesh.area_faces[idx]
    ok = ~np.isnan(d)
    d, area = d[ok], area[ok]
    if not len(d):
        return {}
    tot = area.sum()
    return {
        "minimo_mm": round(float(d.min()), 2),
        "p5_mm": round(float(np.percentile(d, 5)), 2),
        "mediana_mm": round(float(np.median(d)), 2),
        "area_sotto_0_8mm_pct": round(float(area[d < 0.8].sum() / tot * 100), 1),
        "area_sotto_1_2mm_pct": round(float(area[d < 1.2].sum() / tot * 100), 1),
        "nota": "0,8 mm = 2 linee con ugello 0,4: sotto questo spessore le pareti escono incomplete",
    }


def classifica_facce(mesh, soglia=SOGLIA_SUPPORTI, rng=None):
    """Per un pezzo già orientato (piatto a z=zmin): quali facce chiedono supporti e da dove."""
    rng = rng or np.random.default_rng(0)
    zmin = mesh.bounds[0, 2]
    nz = mesh.face_normals[:, 2]
    zc = mesh.triangles_center[:, 2]
    appoggio = (nz < -0.99) & (mesh.triangles[:, :, 2].max(axis=1) < zmin + 0.05)
    sporgenza = (nz < -math.cos(math.radians(soglia))) & ~appoggio
    tipo = np.zeros(len(mesh.faces), dtype=np.int8)       # 0 ok, 1 supporto dal piatto, 2 supporto sul pezzo
    distanza = np.zeros(len(mesh.faces))
    idx = np.where(sporgenza)[0]
    if len(idx):
        orig = mesh.triangles_center[idx] + np.array([0, 0, -1e-3])
        giu = np.tile([0.0, 0.0, -1.0], (len(idx), 1))
        loc, iray, _ = mesh.ray.intersects_location(orig, giu, multiple_hits=False)
        colpito = np.zeros(len(idx), bool)
        colpito[iray] = True
        dist = zc[idx] - zmin
        dist[iray] = orig[iray, 2] - loc[:, 2]
        tipo[idx] = np.where(colpito, 2, 1)
        distanza[idx] = dist
    return tipo, distanza, appoggio


def valuta_orientamento(mesh, soglia=SOGLIA_SUPPORTI):
    tipo, dist, appoggio = classifica_facce(mesh, soglia)
    area_xy = mesh.area_faces * np.abs(mesh.face_normals[:, 2])   # proiezione sul piatto
    dal_piatto, sul_pezzo = tipo == 1, tipo == 2
    contatto = float(mesh.area_faces[appoggio].sum())
    h = float(mesh.extents[2])
    return {
        "altezza_mm": round(h, 1),
        "area_appoggio_mm2": round(contatto, 1),
        "supporti_dal_piatto_area_mm2": round(float(area_xy[dal_piatto].sum()), 1),
        "supporti_sul_pezzo_area_mm2": round(float(area_xy[sul_pezzo].sum()), 1),
        "volume_supporti_stimato_mm3": round(float((area_xy * dist)[tipo > 0].sum()), 0),
        "altezza_max_supporti_mm": round(float(dist[tipo > 0].max()) if (tipo > 0).any() else 0.0, 1),
        "rapporto_altezza_appoggio": round(h / math.sqrt(contatto), 2) if contatto > 0 else None,
    }


APPOGGIO_MINIMO = 10.0    # mm2: sotto questo il pezzo poggia su punte o spigoli


def orientamenti(mesh, n=6):
    """Orientamento del file + pose stabili più probabili, ognuna con la sua valutazione."""
    trasf, prob = mesh.compute_stable_poses(n_samples=1)
    candidati = [(np.eye(4), None, "come nel file")]
    candidati += [(T, p, "posa stabile") for T, p in list(zip(trasf, prob))[:n]]
    out = []
    for T, p, origine in candidati:
        m = mesh.copy()
        m.apply_transform(T)
        m.apply_translation(-m.bounds[0])          # angolo in basso a sinistra sul piatto
        v = valuta_orientamento(m)
        v["origine"] = origine
        v["probabilita_appoggio"] = round(float(p), 3) if p is not None else None
        avvisi = []
        if v["area_appoggio_mm2"] < APPOGGIO_MINIMO:
            avvisi.append("appoggia su punte o spigoli: senza brim o supporti si stacca")
        if v["supporti_sul_pezzo_area_mm2"] > 0:
            avvisi.append("alcune sporgenze poggerebbero sul pezzo stesso (supporti difficili da togliere)")
        v["avvisi"] = avvisi
        out.append({"trasformazione": T.tolist(), **v})
    # punteggio semplice (più basso = meglio): i supporti sul pezzo pesano il triplo,
    # l'appoggio su punte è penalizzato perché il pezzo rischia di staccarsi
    for o in out:
        o["punteggio"] = round(o["supporti_dal_piatto_area_mm2"] + 3 * o["supporti_sul_pezzo_area_mm2"]
                               + 0.02 * o["volume_supporti_stimato_mm3"]
                               + (200 if o["area_appoggio_mm2"] < APPOGGIO_MINIMO else 0), 1)
    out.sort(key=lambda o: o["punteggio"])
    for i, o in enumerate(out, 1):
        o["id"] = i
    return out


def analizza(percorso):
    rng = np.random.default_rng(0)
    mesh = carica(percorso)
    aperti = bordi_aperti(mesh)
    # anche con pochi bordi aperti il volume resta una buona stima
    vol_cm3 = abs(float(mesh.volume)) / 1000 if aperti < 0.01 * len(mesh.edges_unique) else None
    info = {
        "file": str(percorso),
        "facce": int(len(mesh.faces)),
        "chiuso_stagno": bool(mesh.is_watertight),
        "bordi_aperti": aperti,
        "normali_coerenti": bool(mesh.is_winding_consistent),
        "corpi_separati": int(len(mesh.split(only_watertight=False))),
        "dimensioni_mm": [round(float(x), 1) for x in mesh.extents],
        "volume_cm3": round(vol_cm3, 2) if vol_cm3 else None,
        "superficie_cm2": round(float(mesh.area) / 100, 1),
        "peso_g_se_pieno": {k: round(vol_cm3 * d, 1) for k, d in DENSITA.items()} if vol_cm3 else None,
        "spessori": spessori(mesh, rng),
        "soglia_supporti_gradi": SOGLIA_SUPPORTI,
    }
    info["orientamenti"] = orientamenti(mesh)
    return mesh, info


if __name__ == "__main__":
    import json, sys
    _, dati = analizza(sys.argv[1])
    for o in dati["orientamenti"]:
        o.pop("trasformazione")
    print(json.dumps(dati, indent=2, ensure_ascii=False))
