"""La tua stampante e i tuoi materiali: Claude li usa come contesto. Modificali qui."""
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent
LAVORI = CARTELLA / "lavori"          # una sottocartella per ogni analisi
DIARIO = CARTELLA / "diario.jsonl"     # una riga per ogni stampa annotata
FOTO = CARTELLA / "foto"

STAMPANTE = {
    "modello": "Elegoo Centauri Carbon",
    "ugello": "0,4 mm",
    "caratteristiche": "CoreXY, camera chiusa, piatto riscaldato",
    "slicer": "ElegooSlicer (derivato da OrcaSlicer), interfaccia in italiano",
    "profilo_processo_abituale": "0.16mm Optimal @Elegoo CC 0.4 nozzle",
}

UGELLO_MM = 0.4
VOLUME_STAMPA = (256, 256, 256)      # mm, Centauri Carbon: usato dall'add-on augura

FILAMENTI =["PLA", "PETG", "PLA-CF", "ASA", "ABS", "TPU 95A"]

MODELLI = {"Opus (più accurato)": "opus", "Sonnet (più rapido)": "sonnet"}
