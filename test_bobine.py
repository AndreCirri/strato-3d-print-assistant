import tempfile
import unittest
from pathlib import Path

import bobine


class BobineTest(unittest.TestCase):
    def test_registra_consumi_pesate_e_costo(self):
        with tempfile.TemporaryDirectory() as cartella:
            percorso = Path(cartella) / "bobine.json"
            voce = bobine.aggiungi({
                "nome": "PETG nero", "materiale": "PETG", "peso_netto_g": 1000,
                "residuo_g": 500, "tara_g": 220, "costo_eur": 25,
            }, percorso)

            bobine.consuma(voce["id"], 50, percorso)
            self.assertEqual(bobine.tutte(percorso)[0]["residuo_g"], 450)
            bobine.aggiorna_da_pesata(voce["id"], 620, percorso)
            self.assertEqual(bobine.tutte(percorso)[0]["residuo_g"], 400)
            stima = bobine.stime(bobine.tutte(percorso), "PETG", 100)[0]
            self.assertTrue(stima["sufficiente"])
            self.assertEqual(stima["costo_stimato_eur"], 2.5)


if __name__ == "__main__":
    unittest.main()
