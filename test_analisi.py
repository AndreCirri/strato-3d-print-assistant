import unittest

import numpy as np
import trimesh

from analisi import classifica_facce


def scatola(dimensioni, centro_z):
    corpo = trimesh.creation.box(extents=dimensioni)
    corpo.apply_translation([0, 0, centro_z])
    return corpo


class ClassificaFacceTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
