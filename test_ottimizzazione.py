import unittest

import ottimizzazione


VARIANTI = [
    {"id": "dettaglio", "nome": "Dettaglio", "descrizione": "fine",
     "impostazioni": {"layer_height": "0.12", "wall_loops": "3", "sparse_infill_density": "20%"}},
    {"id": "bilanciato", "nome": "Bilanciato", "descrizione": "base", "riferimento": True,
     "impostazioni": {"layer_height": "0.16", "wall_loops": "2", "sparse_infill_density": "15%"}},
    {"id": "veloce", "nome": "Veloce", "descrizione": "rapido",
     "impostazioni": {"layer_height": "0.24", "wall_loops": "2", "sparse_infill_density": "10%"}},
]


def risultato(tempo, pezzo, supporti=1, brim=0):
    return {"tempo": f"{tempo}s", "tempo_s": tempo, "pezzo_g": pezzo,
            "supporti_g": supporti, "brim_g": brim, "strati": 10}


class OttimizzazioneTest(unittest.TestCase):
    def setUp(self):
        self.orientamenti = [
            {"id": 4, "slicer": risultato(100, 10)},
            {"id": 2, "slicer": risultato(90, 12)},
            {"id": 9, "slicer": risultato(80, 8)},
        ]
        self.extra = [
            {"orientamento_id": 4, "variante_id": "dettaglio", "risultato": risultato(150, 13)},
            {"orientamento_id": 4, "variante_id": "veloce", "risultato": risultato(70, 9)},
            {"orientamento_id": 2, "variante_id": "dettaglio", "risultato": risultato(130, 14)},
            {"orientamento_id": 2, "variante_id": "veloce", "risultato": risultato(60, 8)},
        ]

    def test_riusa_il_riferimento_e_limita_gli_orientamenti(self):
        opt = ottimizzazione.costruisci(self.orientamenti, VARIANTI, self.extra, "precisione delle misure", 2)
        self.assertEqual(opt["orientamenti_confrontati"], [4, 2])
        self.assertEqual(len(opt["risultati"]), 6)
        base = next(r for r in opt["risultati"]
                    if r["orientamento_id"] == 4 and r["variante_id"] == "bilanciato")
        self.assertEqual(base["tempo_s"], 100)
        self.assertEqual(base["materiale_g"], 11)

    def test_calcola_i_delta_rispetto_al_bilanciato_dello_stesso_orientamento(self):
        opt = ottimizzazione.costruisci(self.orientamenti, VARIANTI, self.extra, "velocità di stampa", 2)
        veloce = next(r for r in opt["risultati"]
                      if r["orientamento_id"] == 4 and r["variante_id"] == "veloce")
        self.assertEqual(veloce["delta_tempo_pct"], -30)
        self.assertEqual(veloce["delta_materiale_pct"], -9.1)

    def test_velocita_e_materiale_usano_i_valori_misurati(self):
        opt = ottimizzazione.costruisci(self.orientamenti, VARIANTI, self.extra, "velocità di stampa", 2)
        self.assertEqual(opt["raccomandazione"]["orientamento_id"], 2)
        self.assertEqual(opt["raccomandazione"]["variante_id"], "veloce")
        ottimizzazione.aggiorna_priorita(opt, "poco materiale")
        self.assertEqual(opt["raccomandazione"]["orientamento_id"], 2)

    def test_qualita_privilegia_dettaglio_sul_primo_orientamento(self):
        opt = ottimizzazione.costruisci(self.orientamenti, VARIANTI, self.extra, "superficie bella", 2)
        self.assertEqual(opt["raccomandazione"]["orientamento_id"], 4)
        self.assertEqual(opt["raccomandazione"]["variante_id"], "dettaglio")

    def test_un_errore_resta_visibile_e_non_viene_raccomandato(self):
        extra = list(self.extra)
        extra[-1] = {"orientamento_id": 2, "variante_id": "veloce",
                     "risultato": {"errore": "slicer fallito"}}
        opt = ottimizzazione.costruisci(self.orientamenti, VARIANTI, extra, "velocità di stampa", 2)
        self.assertEqual(opt["raccomandazione"]["orientamento_id"], 4)
        errore = next(r for r in opt["risultati"] if r.get("errore"))
        self.assertEqual(errore["errore"], "slicer fallito")


if __name__ == "__main__":
    unittest.main()
