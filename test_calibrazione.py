import unittest

import calibrazione


class CalibrazioneTest(unittest.TestCase):
    def test_propone_correzioni_solo_per_problemi_ricorrenti_dello_stesso_materiale(self):
        voci = [
            {"materiale": "PETG", "problemi": ["fili tra le parti (stringing)"], "temperatura_ugello_c": 245},
            {"materiale": "PETG", "problemi": ["fili tra le parti (stringing)"], "temperatura_ugello_c": 235},
            {"materiale": "PLA", "problemi": ["pezzo fragile"]},
        ]

        esito = calibrazione.analizza(voci, "PETG")

        self.assertTrue(esito["dati_sufficienti"])
        self.assertEqual(esito["problemi_ricorrenti"][0]["occorrenze"], 2)
        self.assertEqual(esito["mediane_registrate"], {})
        self.assertNotIn("pezzo fragile", esito["problemi_osservati"])

    def test_non_chiama_previsione_una_sola_osservazione(self):
        esito = calibrazione.analizza([{"materiale": "PLA", "problemi": ["pezzo fragile"]}], "PLA")
        self.assertFalse(esito["dati_sufficienti"])
        self.assertEqual(esito["problemi_ricorrenti"], [])


if __name__ == "__main__":
    unittest.main()
