import unittest
from unittest.mock import patch

import trimesh

from anteprima import crea


class AnteprimaTest(unittest.TestCase):
    def test_formati_mesh_e_geometrie_diverse(self):
        cubo = trimesh.creation.box()
        for formato in ('stl', 'obj', '3mf'):
            with self.subTest(formato=formato):
                dati = cubo.export(file_type=formato)
                if isinstance(dati, str):
                    dati = dati.encode()
                self.assertTrue(crea(dati, '.' + formato).startswith(b'\x89PNG\r\n\x1a\n'))
        sfera = trimesh.creation.icosphere(subdivisions=1)
        self.assertNotEqual(crea(cubo.export(file_type='stl'), '.stl'),
                            crea(sfera.export(file_type='stl'), '.stl'))

    def test_file_vuoto_e_step_senza_addon(self):
        with self.assertRaises(ValueError):
            crea(b'solid vuoto\nendsolid vuoto', '.stl')
        with patch('augura_addon.disponibile', return_value=False):
            with self.assertRaisesRegex(ValueError, 'augura'):
                crea(b'STEP', '.step')

    def test_step_usa_conversione_locale(self):
        def converti(originale, destinazione):
            self.assertEqual(originale.read_bytes(), b'STEP')
            trimesh.creation.box().export(destinazione)

        with patch('augura_addon.disponibile', return_value=True), \
             patch('augura_addon.step_in_stl', side_effect=converti) as conversione:
            self.assertTrue(crea(b'STEP', '.step').startswith(b'\x89PNG'))
            conversione.assert_called_once()


if __name__ == '__main__':
    unittest.main()
