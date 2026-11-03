import unittest

import stampabilita


class StampabilitaTest(unittest.TestCase):
    def test_segnala_dimensioni_pareti_e_supporti_critici(self):
        dati = {
            "dimensioni_mm": [300, 20, 20], "chiuso_stagno": True, "corpi_separati": 1,
            "spessori": {"area_sotto_0_8mm_pct": 12},
            "orientamenti": [{
                "id": 4, "si_ribalta": False, "rapporto_altezza_appoggio": 5,
                "supporti_sul_pezzo_area_mm2": 20, "altezza_max_supporti_mm": 60,
                "brim_consigliato": True, "brim_motivo": "appoggio piccolo",
                "slicer": {"pezzo_g": 10, "supporti_g": 5},
            }],
        }

        esito = stampabilita.valuta(dati)
        codici = {r["codice"] for r in esito["controlli"]}

        self.assertIn("fuori_volume", codici)
        self.assertIn("pareti_sottili", codici)
        self.assertIn("pezzo_slanciato", codici)
        self.assertIn("molti_supporti", codici)
        self.assertEqual(esito["orientamento_valutato"], 4)


if __name__ == "__main__":
    unittest.main()
