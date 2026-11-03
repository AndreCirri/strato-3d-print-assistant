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


def valuta(orientamenti, direzione, sollecitazione, parte_critica="nessuna indicata", spessori=None,
           fissaggio=None, carico=None, vincoli="", zona_critica=""):
    """Confronta quanto il carico dichiarato agisce lungo la normale dei layer.

    Non stima tensioni o carichi di rottura: produce un indice relativo utile a confrontare
    gli orientamenti già analizzati.
    """
    vettore = DIREZIONI.get(direzione)
    if not orientamenti or vettore is None or sollecitazione in ("non specificata", "urti ripetuti"):
        return None
    asse = vettore.copy()
    braccio = None
    avvisi = []
    if fissaggio is not None and carico is not None:
        distanza = np.asarray(carico, dtype=float) - np.asarray(fissaggio, dtype=float)
        lunghezza = float(np.linalg.norm(distanza))
        if lunghezza < 1e-6 or not np.isfinite(lunghezza):
            return None
        asse = distanza / lunghezza
        braccio = round(float(np.linalg.norm(np.cross(distanza, vettore))), 2)
    elif sollecitazione in ('flessione', 'torsione'):
        avvisi.append("Senza punti di fissaggio/carico, l'asse selezionato è assunto come asse della trave o dell'albero.")
    tensori = []
    if sollecitazione == 'torsione':
        riferimento = np.eye(3)[np.argmin(np.abs(asse))]
        u = np.cross(asse, riferimento)
        u /= np.linalg.norm(u)
        v = np.cross(asse, u)
        for angolo in np.linspace(0, 2 * np.pi, 32, endpoint=False):
            tangente = u * np.cos(angolo) + v * np.sin(angolo)
            tensori.append(np.outer(asse, tangente) + np.outer(tangente, asse))
        avvisi.append('Torsione: confronto sul caso peggiore di 32 direzioni di taglio attorno all’asse; geometria della sezione non simulata.')
    else:
        if sollecitazione not in ('flessione',):
            asse = vettore
        tensore = np.outer(asse, asse)
        tensori = [-tensore] if sollecitazione == 'compressione' else [tensore]
    if sollecitazione == 'flessione':
        avvisi.append('Flessione: modello locale di trave con tensione longitudinale; non simula il vincolo o le concentrazioni di tensione.')
        if braccio == 0:
            avvisi.append('Forza e braccio sono allineati: questi punti non descrivono una flessione; verifica il caso di carico.')
    righe = []
    for posizione, orientamento in enumerate(orientamenti, 1):
        trasformazione = np.asarray(orientamento["trasformazione"], dtype=float)
        normale = trasformazione[:3, :3].T @ np.array([0., 0., 1.])
        aperture, tagli = [], []
        for tensore in tensori:
            trazione = tensore @ normale
            normale_tensione = float(normale @ trazione)
            aperture.append(max(0., normale_tensione))
            tagli.append(float(np.linalg.norm(trazione - normale_tensione * normale)))
        apertura, taglio = max(aperture), max(tagli)
        indice = round(min(1., max(apertura, .5 * taglio)), 3)
        righe.append({
            "orientamento_id": orientamento["id"],
            "posizione_attuale": posizione,
            "carico_tra_strati_pct": round(apertura * 100),
            "taglio_relativo_pct": round(taglio * 100),
            "rischio_delaminazione": _livello(indice),
            "indice": indice,
        })

    righe.sort(key=lambda r: (r["indice"], r["posizione_attuale"]))
    migliore = righe[0]
    pareti = 3
    if sollecitazione in {"trazione", "flessione", "torsione"}:
        pareti = 4
    if migliore["rischio_delaminazione"] == "alto" or parte_critica in {
            "perno", "linguetta flessibile", "gancio"}:
        pareti = max(pareti, 5)

    if sollecitazione == 'torsione':
        pareti = 5
    p5 = (spessori or {}).get("p5_mm")
    if isinstance(p5, (int, float)) and p5 < 1.2:
        avvisi.append(f"Il 5% più sottile delle pareti misura circa {p5:g} mm: verifica la zona caricata.")
    if parte_critica != "nessuna indicata":
        avvisi.append(f"La parte critica dichiarata è «{parte_critica}»: controlla che le linee layer non la attraversino.")

    if isinstance(p5, (int, float)) and p5 < pareti * .45:
        avvisi.append('Le pareti aggiuntive non ispessiscono il CAD: nelle zone sottili lo slicer potrebbe non riuscire a crearle tutte.')
    return {
        "metodo": "tensioni_ideali_sul_piano_layer_v2",
        "sollecitazione": sollecitazione,
        "direzione": direzione,
        "parte_critica": parte_critica,
        "fissaggio_mm": fissaggio, "punto_carico_mm": carico, "vincoli": vincoli,
        "zona_critica": zona_critica, "braccio_trasversale_mm": braccio,
        "criterio": "Indice relativo = massimo tra apertura e metà del taglio; tensioni normalizzate senza unità",
        "orientamento_consigliato": migliore["orientamento_id"],
        "pareti_consigliate": pareti,
        "risultati": sorted(righe, key=lambda r: r["posizione_attuale"]),
        "avvisi": avvisi,
        "limite": "Confronto relativo: non calcola tensioni, deformazioni o carico di rottura.",
    }
