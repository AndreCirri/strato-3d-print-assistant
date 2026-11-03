import copy
import unittest

import classifica


def orientamento(identificatore, geometrico, supporti_g=None, sul_pezzo=0, brim_g=0,
                  penalita=0, errore=None):
    slicer = {}
    if supporti_g is not None:
        slicer.update({"supporti_g": supporti_g, "brim_g": brim_g, "tempo_s": 60, "pezzo_g": 1})
    if errore:
        slicer["errore"] = errore
    return {
        "id": identificatore,
        "punteggio": geometrico,
        "supporti_sul_pezzo_area_mm2": sul_pezzo,
        "penalita_stabilita": penalita,
        "slicer": slicer,
    }


class ClassificaRealeTest(unittest.TestCase):
    def test_i_grammi_reali_cambiano_la_classifica_senza_cambiare_id(self):
        dati = {"orientamenti": [orientamento(1, 10, 4), orientamento(2, 20, 1)]}
        classifica.applica(dati)
        self.assertEqual([o["id"] for o in dati["orientamenti"]], [2, 1])
        self.assertEqual(dati["orientamenti"][0]["posizione_geometrica"], 2)
        self.assertEqual(dati["classifica"]["metodo"], "sezionamento_reale")

    def test_supporti_sul_pezzo_non_scompaiono_con_supporti_solo_dal_piatto(self):
        dati = {"orientamenti": [orientamento(1, 10, 0, sul_pezzo=1000),
                                  orientamento(2, 20, 2, sul_pezzo=0)]}
        classifica.applica(dati)
        self.assertEqual(dati["orientamenti"][0]["id"], 2)
        penalizzato = next(o for o in dati["orientamenti"] if o["id"] == 1)
        self.assertEqual(penalizzato["supporti_sul_pezzo_stimati_g"], 5)
        self.assertEqual(penalizzato["punteggio_reale"], 15)

    def test_brim_e_stabilita_hanno_peso_esplicito(self):
        dati = {"orientamenti": [orientamento(1, 10, 1, brim_g=4, penalita=200)]}
        classifica.applica(dati)
        o = dati["orientamenti"][0]
        self.assertEqual(o["penalita_stabilita_reale_g"], 1)
        self.assertEqual(o["punteggio_reale"], 3)

    def test_fallback_geometrico_se_non_ci_sono_risultati_validi(self):
        dati = {"orientamenti": [orientamento(1, 30, errore="slicer fallito"),
                                  orientamento(2, 10)]}
        classifica.applica(dati)
        self.assertEqual([o["id"] for o in dati["orientamenti"]], [2, 1])
        self.assertEqual(dati["classifica"]["metodo"], "geometria")
        self.assertTrue(all(o["posizione_reale"] is None for o in dati["orientamenti"]))

    def test_un_errore_parziale_va_dopo_i_risultati_reali(self):
        dati = {"orientamenti": [orientamento(1, 1, errore="slicer fallito"),
                                  orientamento(2, 100, 3)]}
        classifica.applica(dati)
        self.assertEqual([o["id"] for o in dati["orientamenti"]], [2, 1])
        self.assertIsNone(dati["orientamenti"][1]["posizione_reale"])

    def test_applicazione_ripetuta_e_compatibile_con_vecchi_dati(self):
        dati = {"orientamenti": [orientamento(7, 20, 2), orientamento(3, 10, 1)]}
        prima = copy.deepcopy(classifica.applica(dati))
        seconda = classifica.applica(dati)
        self.assertEqual(prima, seconda)
        self.assertEqual(seconda["orientamenti"][0]["punteggio_geometrico"], 10)

    def test_un_risultato_diventato_non_valido_non_conserva_il_vecchio_score(self):
        dati = {"orientamenti": [orientamento(1, 10, 2)]}
        classifica.applica(dati)
        dati["orientamenti"][0]["slicer"] = {"errore": "nuovo errore"}
        classifica.applica(dati)
        self.assertNotIn("punteggio_reale", dati["orientamenti"][0])
        self.assertEqual(dati["classifica"]["metodo"], "geometria")

    def test_punteggio_geometrico_zero_resta_un_valore_valido(self):
        dati = {"orientamenti": [orientamento(2, 1, 1), orientamento(1, 0, 1)]}
        classifica.applica(dati)
        self.assertEqual(dati["orientamenti"][0]["id"], 1)


if __name__ == "__main__":
    unittest.main()
