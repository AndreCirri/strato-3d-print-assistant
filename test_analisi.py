import unittest

import numpy as np
import trimesh

from analisi import (classifica_facce, completa_punteggio_geometrico, misure_globali, unisci_solidi,
                     valuta_orientamento)


def scatola(dimensioni, centro_z):
    corpo = trimesh.creation.box(extents=dimensioni)
    corpo.apply_translation([0, 0, centro_z])
    return corpo


class ClassificaFacceTest(unittest.TestCase):
    def test_unione_preserva_una_cavita_interna_con_guscio_negativo(self):
        esterno = scatola([10,10,10], 5)
        interno = scatola([4,4,4], 5)
        interno.invert()
        m = unisci_solidi(trimesh.util.concatenate([esterno, interno]))
        self.assertAlmostEqual(m.volume, 936)
        self.assertFalse(m.contains([[0,0,5]])[0])
        self.assertTrue(misure_globali(m)['unione_solidi']['misure_affidabili'])
    def test_unione_non_duplica_volume_ne_spessori_interni(self):
        base = scatola([10, 10, 2], 1)
        superiore = scatola([10, 10, 4], 3)
        mesh = unisci_solidi(trimesh.util.concatenate([base, superiore]))
        misure = misure_globali(mesh)
        self.assertAlmostEqual(mesh.volume, 500)
        self.assertAlmostEqual(mesh.area, 400)
        self.assertTrue(misure['unione_solidi']['applicata'])
        self.assertGreaterEqual(misure['spessori']['minimo_mm'], 4.99)

    def test_non_somma_due_volte_le_coperture_sovrapposte(self):
        base = scatola([8, 8, 2], 1)
        seconda_base = base.copy()
        seconda_base.apply_translation([1, 0, 0])
        superiore = scatola([10, 10, 4], 3)
        mesh = trimesh.util.concatenate([base, seconda_base, superiore])

        esito = valuta_orientamento(mesh)

        # Unione delle basi: 9 × 8 = 72 mm²; fondo superiore: 100 mm².
        self.assertAlmostEqual(esito['supporti_dal_piatto_area_mm2'], 28, places=2)

    def test_copertura_parziale_preserva_i_36_mm2_esposti(self):
        base = scatola([8, 8, 2], 1)
        superiore = scatola([10, 10, 4], 3)
        mesh = trimesh.util.concatenate([base, superiore])

        esito = valuta_orientamento(mesh)

        self.assertAlmostEqual(esito['supporti_dal_piatto_area_mm2'], 36, places=2)
        self.assertAlmostEqual(esito['supporti_sul_pezzo_area_mm2'], 0, places=2)

    def test_non_chiede_supporti_per_una_faccia_gia_dentro_un_altro_corpo(self):
        base = scatola([10, 10, 2], 1)
        corpo_sovrapposto = scatola([10, 10, 4], 3)
        mesh = trimesh.util.concatenate([base, corpo_sovrapposto])

        tipo, _, _ = classifica_facce(mesh)

        self.assertFalse(np.any(tipo > 0))

    def test_conserva_il_supporto_se_sotto_la_faccia_ce_un_vuoto_reale(self):
        base = scatola([10, 10, 1], 0.5)
        corpo_sospeso = scatola([10, 10, 1], 2.5)
        mesh = trimesh.util.concatenate([base, corpo_sospeso])

        tipo, _, _ = classifica_facce(mesh)

        self.assertTrue(np.any(tipo == 2))

    def test_supporti_dentro_una_tazza_capovolta_sono_in_cavita(self):
        tazza = trimesh.boolean.difference([scatola([20, 20, 15], 7.5), scatola([16, 16, 13], 6.5)],
                                           engine='manifold')

        esito = valuta_orientamento(tazza)

        # soffitto interno 16 × 16: dal piatto, ma circondato dalle pareti
        self.assertAlmostEqual(esito['supporti_in_cavita_area_mm2'], 256, places=0)
        self.assertAlmostEqual(esito['supporti_dal_piatto_area_mm2'], 256, places=0)
        self.assertTrue(any('cavità' in a for a in completa_punteggio_geometrico(esito)['avvisi']))

    def test_supporti_sotto_un_tunnel_aperto_ai_lati_non_sono_in_cavita(self):
        ponte = trimesh.boolean.difference([scatola([20, 20, 10], 5), scatola([24, 8, 12], 0)],
                                           engine='manifold')

        esito = valuta_orientamento(ponte)

        self.assertGreater(esito['supporti_dal_piatto_area_mm2'], 0)
        self.assertEqual(esito['supporti_in_cavita_area_mm2'], 0)

    def test_tazza_capovolta_pesa_piu_della_stessa_area_libera(self):
        tazza = trimesh.boolean.difference([scatola([20, 20, 15], 7.5), scatola([16, 16, 13], 6.5)],
                                           engine='manifold')
        ponte = trimesh.boolean.difference([scatola([20, 20, 15], 7.5), scatola([24, 16, 26], 0)],
                                           engine='manifold')
        in_cavita = completa_punteggio_geometrico(valuta_orientamento(tazza))
        aperto = completa_punteggio_geometrico(valuta_orientamento(ponte))
        self.assertGreater(in_cavita['punteggio'], aperto['punteggio'])


if __name__ == "__main__":
    unittest.main()
