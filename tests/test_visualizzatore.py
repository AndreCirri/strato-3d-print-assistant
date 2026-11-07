import unittest

import numpy as np
import trimesh

from visualizzatore import COLORI, figura, prepara


class VisualizzatoreTest(unittest.TestCase):
    def test_mesh_completa_dimensioni_e_camera_persistente(self):
        mesh = trimesh.creation.box(extents=[20, 10, 5])
        dati = prepara(mesh.export(file_type='stl'), '.stl')
        self.assertEqual(len(dati['facce']), len(mesh.faces))
        np.testing.assert_allclose(dati['limiti'][0], [-10, -5, 0])
        np.testing.assert_allclose(dati['limiti'][1], [10, 5, 5])
        self.assertIsNone(dati['colori'])
        fig = figura(dati)
        modello = next(t for t in fig.data if t.type == 'mesh3d')
        self.assertEqual(len(modello.i), 12)
        self.assertGreater(len(set(modello.facecolor)), 1)
        self.assertEqual(fig.layout.uirevision, dati['revisione'])
        self.assertEqual(fig.layout.scene.dragmode, 'orbit')

    def test_rotazione_e_nuovo_file_cambiano_revisione(self):
        contenuto = trimesh.creation.box(extents=[20, 10, 5]).export(file_type='stl')
        base = prepara(contenuto, '.stl')
        matrice = trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0])
        ruotato = prepara(contenuto, '.stl', matrice.tolist())
        np.testing.assert_allclose(ruotato['limiti'][1] - ruotato['limiti'][0], [20, 5, 10])
        self.assertNotEqual(base['revisione'], ruotato['revisione'])
        altro = prepara(trimesh.creation.icosphere(subdivisions=1).export(file_type='stl'), '.stl')
        self.assertNotEqual(base['revisione'], altro['revisione'])

    def test_colori_supporti_usano_la_classificazione_geometrica(self):
        # Un cubo sollevato sopra la base richiede supporti sotto la faccia inferiore.
        base = trimesh.creation.box(extents=[20, 20, 2])
        corpo = trimesh.creation.box(extents=[8, 8, 4])
        corpo.apply_translation([0, 0, 10])
        mesh = trimesh.util.concatenate([base, corpo])
        dati = prepara(mesh.export(file_type='stl'), '.stl', supporti=True)
        self.assertEqual(len(dati['colori']), len(dati['facce']))
        self.assertTrue(set(dati['colori']).issubset(COLORI))
        self.assertIn(COLORI[2], dati['colori'])

    def test_file_invalido(self):
        with self.assertRaises(ValueError):
            prepara(b'solid vuoto\nendsolid vuoto', '.stl')


if __name__ == '__main__':
    unittest.main()
