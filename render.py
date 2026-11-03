"""Immagini del pezzo orientato, con le sporgenze colorate (per te e per Claude)."""
import numpy as np
import trimesh
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

from analisi import classifica_facce

FACCE_MAX = 12000                         # oltre si alleggerisce la mesh solo per disegnarla
COLORI = {0: (0.80, 0.82, 0.86), 1: (0.86, 0.22, 0.20), 2: (0.98, 0.62, 0.10), 3: (0.58, 0.30, 0.72)}
LUCE = np.array([0.35, -0.45, 0.82]) / np.linalg.norm([0.35, -0.45, 0.82])


def orienta(mesh, T):
    m = mesh.copy()
    m.apply_transform(np.array(T))
    m.apply_translation(-m.bounds[0])
    return m


def _alleggerisci(m):
    """Mesh da disegnare: matplotlib ordina i triangoli per profondità media, quindi quelli
    lunghi e sottili si sovrappongono male. Si suddividono i grandi e si sfoltiscono i troppi."""
    if len(m.faces) > FACCE_MAX:
        try:
            m = m.simplify_quadric_decimation(face_count=FACCE_MAX)
        except Exception:
            pass
    for divisore in (35, 25, 18, 12):
        try:
            v, f = trimesh.remesh.subdivide_to_size(m.vertices, m.faces, max_edge=m.extents.max() / divisore, max_iter=8)
        except Exception:
            break
        if len(f) <= 3 * FACCE_MAX:
            return trimesh.Trimesh(v, f, process=False)
    return m


def _disegna(ax, m, elev, azim, titolo=None):
    tipo, _, _ = classifica_facce(m)
    base = np.array([COLORI[int(t)] for t in tipo])
    luce = 0.45 + 0.55 * np.clip(m.face_normals @ LUCE, 0, 1)
    colori = np.clip(base * luce[:, None], 0, 1)
    # si disegnano solo le facce rivolte verso chi guarda: niente facce interne in trasparenza
    e, a = np.radians(elev), np.radians(azim)
    occhio = np.array([np.cos(e) * np.cos(a), np.cos(e) * np.sin(a), np.sin(e)])
    visibili = m.face_normals @ occhio > 0
    lo, hi = m.bounds
    pad = 0.15 * (hi - lo).max()
    # piatto di stampa sotto, pezzo sopra: ordine fisso invece di quello calcolato da matplotlib
    ax.computed_zorder = False
    xs, ys = [lo[0] - pad, hi[0] + pad], [lo[1] - pad, hi[1] + pad]
    ax.add_collection3d(Poly3DCollection([[(xs[0], ys[0], 0), (xs[1], ys[0], 0), (xs[1], ys[1], 0), (xs[0], ys[1], 0)]],
                                         facecolors=(0.55, 0.62, 0.70, 0.35), edgecolors="none", zorder=1))
    # bordo dello stesso colore: chiude le fessure dell'antialiasing tra triangoli vicini
    ax.add_collection3d(Poly3DCollection(m.triangles[visibili], facecolors=colori[visibili],
                                         edgecolors=colori[visibili], linewidths=0.3, zorder=2))
    ax.set_xlim(xs); ax.set_ylim(ys); ax.set_zlim(0, max(hi[2], 1) + pad)
    ax.set_box_aspect((xs[1] - xs[0], ys[1] - ys[0], max(hi[2], 1) + pad))
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()
    if titolo:
        ax.set_title(titolo, fontsize=10)


def griglia_orientamenti(mesh, orientamenti, percorso):
    n = len(orientamenti)
    col = min(4, n); righe = (n + col - 1) // col
    fig = plt.figure(figsize=(4 * col, 3.6 * righe))
    for i, o in enumerate(orientamenti):
        ax = fig.add_subplot(righe, col, i + 1, projection="3d")
        m = _alleggerisci(orienta(mesh, o["trasformazione"]))
        _disegna(ax, m, 22, -55, f"{o['id']}. {o['origine']} - h {o['altezza_mm']} mm")
    fig.suptitle("Orientamenti candidati (rosso: supporto dal piatto, viola: dal piatto in una cavità, arancione: sul pezzo)", fontsize=11)
    fig.tight_layout()
    fig.savefig(percorso, dpi=90)
    plt.close(fig)


def viste(mesh, T, percorso, titolo=""):
    m = _alleggerisci(orienta(mesh, T))
    fig = plt.figure(figsize=(12, 4.2))
    for i, (elev, azim, nome) in enumerate([(25, -55, "3/4 dall'alto"), (-25, 125, "3/4 da sotto"), (0, -90, "di fianco")]):
        ax = fig.add_subplot(1, 3, i + 1, projection="3d")
        _disegna(ax, m, elev, azim, nome)
    fig.suptitle(titolo, fontsize=11)
    fig.tight_layout()
    fig.savefig(percorso, dpi=100)
    plt.close(fig)
