"""Valutazione euristica della resistenza rispetto alla direzione degli strati."""
import numpy as np


DIREZIONI = {
    "asse X del file": np.array([1.0, 0.0, 0.0]),
    "asse Y del file": np.array([0.0, 1.0, 0.0]),
    "asse Z del file": np.array([0.0, 0.0, 1.0]),
}


def _livello(indice):
    if indice >= 0.7:
        return "alto"
    if indice >= 0.3:
        return "medio"
    return "basso"


def _fattore_sollecitazione(sollecitazione):
    return {
        "trazione": 1.0,
        "flessione": 0.9,
        "urti ripetuti": 0.85,
        "torsione": 0.65,
        "compressione": 0.35,
    }.get(sollecitazione, 0.75)


def valuta(orientamenti, direzione, sollecitazione, parte_critica="nessuna indicata", spessori=None):
    """Confronta quanto il carico dichiarato agisce lungo la normale dei layer.

    Non stima tensioni o carichi di rottura: produce un indice relativo utile a confrontare
    gli orientamenti già analizzati.
    """
    vettore = DIREZIONI.get(direzione)
    if not orientamenti or vettore is None or sollecitazione in ("non specificata", "torsione", "urti ripetuti"):
        return None

    fattore = _fattore_sollecitazione(sollecitazione)
    righe = []
    for posizione, orientamento in enumerate(orientamenti, 1):
        trasformazione = np.asarray(orientamento["trasformazione"], dtype=float)
        nel_piatto = trasformazione[:3, :3] @ vettore
        componente_z = min(1.0, abs(float(nel_piatto[2])))
        indice = round(componente_z * fattore, 2)
        righe.append({
            "orientamento_id": orientamento["id"],
            "posizione_attuale": posizione,
            "carico_tra_strati_pct": round(componente_z * 100),
            "rischio_delaminazione": _livello(indice),
            "indice": indice,
        })

    righe.sort(key=lambda r: (r["indice"], r["posizione_attuale"]))
    migliore = righe[0]
    pareti = 3
    if sollecitazione in {"trazione", "flessione", "torsione", "urti ripetuti"}:
        pareti = 4
    if migliore["rischio_delaminazione"] == "alto" or parte_critica in {
            "perno", "linguetta flessibile", "gancio"}:
        pareti = max(pareti, 5)

    avvisi = []
    p5 = (spessori or {}).get("p5_mm")
    if isinstance(p5, (int, float)) and p5 < 1.2:
        avvisi.append(f"Il 5% più sottile delle pareti misura circa {p5:g} mm: verifica la zona caricata.")
    if parte_critica != "nessuna indicata":
        avvisi.append(f"La parte critica dichiarata è «{parte_critica}»: controlla che le linee layer non la attraversino.")

    return {
        "metodo": "euristica_direzione_strati",
        "sollecitazione": sollecitazione,
        "direzione": direzione,
        "parte_critica": parte_critica,
        "orientamento_consigliato": migliore["orientamento_id"],
        "pareti_consigliate": pareti,
        "risultati": sorted(righe, key=lambda r: r["posizione_attuale"]),
        "avvisi": avvisi,
        "limite": "Confronto relativo: non calcola tensioni, deformazioni o carico di rottura.",
    }
