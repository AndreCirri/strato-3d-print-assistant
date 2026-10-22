"""Analisi geometrica di un STL per la stampa FDM. Solo calcoli: nessuna AI qui.

Tutte le misure sono in mm. Gli orientamenti candidati sono le pose stabili del pezzo
(le facce su cui può appoggiare sul piatto) calcolate da trimesh.
"""
import math
import warnings
from collections import Counter
import numpy as np
import trimesh
from shapely.geometry import MultiPoint, Point

import orienta_slicer

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
    if len(iray):
        d[iray] = np.linalg.norm(np.asarray(loc).reshape(-1, 3) - orig[iray], axis=1)
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
        dist = zc[idx] - zmin
        if len(iray):                      # nessun raggio a segno: tutte le sporgenze vanno al piatto
            colpito[iray] = True
            dist[iray] = orig[iray, 2] - np.asarray(loc).reshape(-1, 3)[:, 2]
        tipo[idx] = np.where(colpito, 2, 1)
        distanza[idx] = dist
    return tipo, distanza, appoggio


def ribaltamento(mesh, tolleranza=0.05):
    """Il baricentro cade dentro l'impronta sul piatto? L'impronta è il contorno convesso
    di tutti i punti che toccano il piatto (anche punte lontane tra loro, come perno e linguetta)."""
    zmin = mesh.bounds[0, 2]
    punti = mesh.vertices[mesh.vertices[:, 2] < zmin + tolleranza][:, :2]
    impronta = MultiPoint([tuple(p) for p in punti]).convex_hull
    try:
        cm = mesh.center_mass if mesh.is_volume else mesh.centroid
    except Exception:
        cm = mesh.centroid
    baricentro = Point(float(cm[0]), float(cm[1]))
    dentro = impronta.buffer(1e-6).contains(baricentro)
    bordo = impronta.exterior if impronta.geom_type == "Polygon" else impronta
    margine = bordo.distance(baricentro) * (1 if dentro else -1)
    return {"si_ribalta": not dentro, "margine_baricentro_mm": round(float(margine), 1),
            "area_impronta_mm2": round(float(impronta.area), 1)}


def consiglio_brim(contatto, altezza, ribalta):
    motivi = []
    if ribalta:
        motivi.append("il baricentro cade fuori dall'appoggio")
    if contatto < 30:
        motivi.append(f"appoggio piccolo ({contatto:.0f} mm²)")
    rapporto = altezza / math.sqrt(contatto) if contatto > 0 else float("inf")
    if rapporto > 4:
        motivi.append("pezzo alto rispetto all'appoggio (rapporto "
                      + ("infinito" if math.isinf(rapporto) else f"{rapporto:.1f}") + ")")
    return {"brim_consigliato": bool(motivi), "brim_motivo": "; ".join(motivi)}


def valuta_orientamento(mesh, soglia=SOGLIA_SUPPORTI):
    tipo, dist, appoggio = classifica_facce(mesh, soglia)
    area_xy = mesh.area_faces * np.abs(mesh.face_normals[:, 2])   # proiezione sul piatto
    dal_piatto, sul_pezzo = tipo == 1, tipo == 2
    contatto = float(mesh.area_faces[appoggio].sum())
    h = float(mesh.extents[2])
    rib = ribaltamento(mesh)
    ingombro = MultiPoint([tuple(p) for p in mesh.convex_hull.vertices[:, :2]]).convex_hull.area
    return {
        **rib,
        **consiglio_brim(contatto, h, rib["si_ribalta"]),
        "altezza_mm": round(h, 1),
        "ingombro_sul_piatto_mm2": round(float(ingombro), 1),
        "area_appoggio_mm2": round(contatto, 1),
        "supporti_dal_piatto_area_mm2": round(float(area_xy[dal_piatto].sum()), 1),
        "supporti_sul_pezzo_area_mm2": round(float(area_xy[sul_pezzo].sum()), 1),
        "volume_supporti_stimato_mm3": round(float((area_xy * dist)[tipo > 0].sum()), 0),
        "altezza_max_supporti_mm": round(float(dist[tipo > 0].max()) if (tipo > 0).any() else 0.0, 1),
        "rapporto_altezza_appoggio": round(h / math.sqrt(contatto), 2) if contatto > 0 else None,
    }


APPOGGIO_MINIMO = 10.0    # mm2: sotto questo il pezzo poggia su punte o spigoli
# Un pezzo instabile (su spigoli o che si ribalta) va tenuto su da brim o supporti per tutta la
# sua ombra sul piatto: la penalità vale quindi come sostenere tutto l'ingombro, scalata col pezzo.
PESO_INSTABILE = 1.0      # mm2 di penalità per mm2 di ingombro, per ciascun problema
PENALITA_MINIMA = 200.0   # per pezzi minuscoli, dove l'ingombro sarebbe trascurabile


def penalita_stabilita(o):
    unita = max(PENALITA_MINIMA, PESO_INSTABILE * o["ingombro_sul_piatto_mm2"])
    su_spigoli = o["area_appoggio_mm2"] < APPOGGIO_MINIMO
    return unita * (int(su_spigoli) + int(o["si_ribalta"]))


NOMI_SLICER = {"interfaccia": "slicer, pulsante Orienta", "riga_di_comando": "slicer, riga di comando"}


def orientamenti(mesh, n=6, scelte_slicer=()):
    """Orientamento del file + pose stabili più probabili + scelte dello slicer, ognuna valutata.
    Ogni candidato ha anche il costo che gli darebbe il pulsante Orienta dello slicer."""
    trasf, prob = mesh.compute_stable_poses(n_samples=1)
    candidati = [(np.eye(4), None, "come nel file")]
    candidati += [(T, p, "posa stabile") for T, p in list(zip(trasf, prob))[:n]]
    for s in scelte_slicer:
        # se la scelta dello slicer coincide con un candidato, si segna su quello
        if not any(orienta_slicer.direzione_su(T) @ np.array(s["su"]) > 0.999 for T, _, _ in candidati):
            candidati.append((np.array(s["trasformazione"]), None, NOMI_SLICER[s["modo"]]))
    scafo = mesh.convex_hull
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
        if v["si_ribalta"]:
            avvisi.append("si ribalta: il baricentro è fuori dall'appoggio, lo reggono solo i supporti")
        if v["brim_consigliato"]:
            avvisi.append("serve il brim: " + v["brim_motivo"])
        v["avvisi"] = avvisi
        su = orienta_slicer.direzione_su(T)
        v["costo_slicer"] = round(orienta_slicer.costo(mesh, su, SOGLIA_SUPPORTI, scafo)[0], 3)
        v["scelto_da_slicer"] = [NOMI_SLICER[s["modo"]] for s in scelte_slicer if su @ np.array(s["su"]) > 0.999]
        out.append({"trasformazione": T.tolist(), **v})
    # punteggio semplice (più basso = meglio): i supporti sul pezzo pesano il triplo,
    # l'appoggio su spigoli e il ribaltamento costano quanto sostenere tutto l'ingombro
    for o in out:
        o["penalita_stabilita"] = round(penalita_stabilita(o), 1)
        o["punteggio"] = round(o["supporti_dal_piatto_area_mm2"] + 3 * o["supporti_sul_pezzo_area_mm2"]
                               + 0.02 * o["volume_supporti_stimato_mm3"] + o["penalita_stabilita"], 1)
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
    scelte = [orienta_slicer.scelta_slicer(mesh, SOGLIA_SUPPORTI, modo) for modo in ("interfaccia", "riga_di_comando")]
    info["orientamenti"] = orientamenti(mesh, scelte_slicer=scelte)
    info["confronto_slicer"] = confronto_slicer(info["orientamenti"], scelte)
    return mesh, info


CAMPI_CONFRONTO = ["altezza_mm", "area_appoggio_mm2", "supporti_dal_piatto_area_mm2", "supporti_sul_pezzo_area_mm2",
                   "volume_supporti_stimato_mm3", "si_ribalta", "brim_consigliato", "punteggio", "costo_slicer"]


def confronto_slicer(orientamenti, scelte):
    """Le scelte dell'orientamento automatico dello slicer contro il primo della nostra classifica."""
    nostro = orientamenti[0]
    out = {"nota": "Orientamento automatico di OrcaSlicer/ElegooSlicer ricalcolato con lo stesso algoritmo "
                   "(verificato sulla riga di comando di ElegooSlicer). Il pulsante Orienta dell'interfaccia usa "
                   "la modalità 'area minima dei supporti' e la soglia supporti del profilo; la riga di comando "
                   "usa i parametri predefiniti con angolo 60°.",
           "id_primo_nostra_classifica": nostro["id"], "scelte": []}
    for s in scelte:
        nome = NOMI_SLICER[s["modo"]]
        suo = next(o for o in orientamenti if nome in o["scelto_da_slicer"])
        # pari merito con il nostro primo = d'accordo, anche se è una posa gemella
        concorda = suo is nostro or suo["punteggio"] <= nostro["punteggio"]
        out["scelte"].append({
            "chi": nome, "id": suo["id"], "angolo_gradi": s["angolo_gradi"],
            "concorda_con_nostra_classifica": concorda,
            "differenze": {} if concorda else {c: {"slicer": suo[c], "nostro_primo": nostro[c]} for c in CAMPI_CONFRONTO},
            "dettagli_formula_slicer": s["dettagli"],
        })
    return out


if __name__ == "__main__":
    import json, sys
    _, dati = analizza(sys.argv[1])
    for o in dati["orientamenti"]:
        o.pop("trasformazione")
    print(json.dumps(dati, indent=2, ensure_ascii=False))
