import unittest

import numpy as np

import resistenza


class ResistenzaTest(unittest.TestCase):
    def test_preferisce_lorientamento_che_tiene_il_carico_nel_piano_degli_strati(self):
        ruota_y = np.eye(4)
        ruota_y[:3, :3] = [[0, 0, 1], [0, 1, 0], [-1, 0, 0]]
        orientamenti = [
            {"id": 1, "trasformazione": np.eye(4).tolist()},
            {"id": 2, "trasformazione": ruota_y.tolist()},
        ]

        analisi = resistenza.valuta(orientamenti, "asse Z del file", "trazione")

        self.assertEqual(analisi["orientamento_consigliato"], 2)
        self.assertEqual(analisi["risultati"][0]["rischio_delaminazione"], "alto")
        self.assertEqual(analisi["risultati"][1]["rischio_delaminazione"], "basso")

    def test_non_inventa_un_risultato_senza_carico(self):
        self.assertIsNone(resistenza.valuta([], "asse Z del file", "non specificata"))


if __name__ == "__main__":
    unittest.main()
