"""La tua stampante e i tuoi materiali: Claude li usa come contesto. Modificali qui."""
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent
LAVORI = CARTELLA / "lavori"          # una sottocartella per ogni analisi
DIARIO = CARTELLA / "diario.jsonl"     # una riga per ogni stampa annotata
BOBINE = CARTELLA / "bobine.json"       # inventario personale, non versionato
FOTO = CARTELLA / "foto"

STAMPANTE = {
    "modello": "Elegoo Centauri Carbon",
    "ugello": "0,4 mm",
    "caratteristiche": "CoreXY, camera chiusa, piatto riscaldato",
    "slicer": "ElegooSlicer (derivato da OrcaSlicer), interfaccia in italiano",
    "profilo_processo_abituale": "0.16mm Optimal @Elegoo CC 0.4 nozzle",
}

# Profili di sistema di ElegooSlicer usati per il sezionamento reale (slicer_cli.py)
PROFILO_STAMPANTE = "Elegoo Centauri Carbon 0.4 nozzle"
PROFILO_PROCESSO = "0.16mm Optimal @Elegoo CC 0.4 nozzle"
PROFILO_FILAMENTO = "Elegoo PETG @ECC"
# Gradi rispetto all'orizzontale, come "Angolo di soglia" dello slicer: le superfici meno inclinate
# chiedono supporti. Unico valore: lo usano sia l'analisi geometrica sia il sezionamento reale.
SOGLIA_SUPPORTI = 30
# supporti come nelle tue impostazioni: ad albero, solo dal piatto
SUPPORTI_SEZIONAMENTO = {"enable_support": "1", "support_type": "tree(auto)",
                         "support_threshold_angle": str(SOGLIA_SUPPORTI), "support_on_build_plate_only": "1"}

# Dopo la classifica degli orientamenti, i primi due vengono confrontati con queste varianti.
# "Bilanciato" riusa il sezionamento già eseguito con PROFILO_PROCESSO; non viene lanciato di nuovo.
NUM_ORIENTAMENTI_VARIANTI = 2
VARIANTI_PROCESSO = [
    {
        "id": "dettaglio",
        "nome": "Dettaglio",
        "descrizione": "strati più fini, tre pareti e più riempimento",
        "impostazioni": {"layer_height": "0.12", "wall_loops": "3", "sparse_infill_density": "20%"},
    },
    {
        "id": "bilanciato",
        "nome": "Bilanciato",
        "descrizione": "profilo abituale usato come riferimento",
        "impostazioni": {"layer_height": "0.16", "wall_loops": "2", "sparse_infill_density": "15%"},
        "riferimento": True,
    },
    {
        "id": "veloce",
        "nome": "Veloce",
        "descrizione": "strati più alti e meno riempimento per ridurre tempo e materiale",
        "impostazioni": {"layer_height": "0.24", "wall_loops": "2", "sparse_infill_density": "10%"},
    },
]

UGELLO_MM = 0.4
VOLUME_STAMPA = (256, 256, 256)      # mm, Centauri Carbon: usato dall'add-on augura

FILAMENTI =["PLA", "PETG", "PLA-CF", "ASA", "ABS", "TPU 95A"]

MODELLI = {"Opus (più accurato)": "opus", "Sonnet (più rapido)": "sonnet"}
