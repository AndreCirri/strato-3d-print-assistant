"""Le fasi escluse non devono avviare elaborazioni costose."""
import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import config
import lavorazioni
import analisi
import numpy as np
import trimesh
from persistenza import salva_json


class SceltaAnalisiTest(unittest.TestCase):
    def esegui(self, scelte):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            cartella = Path(tmp)
            salva_json(cartella / 'richiesta.json', scelte)
            salva_json(cartella / 'ingresso.json', {'file': 'pezzo.step', 'sha256': 'prova'})
            dati = {'file': 'pezzo.stl', 'versione_geometria': config.VERSIONE_GEOMETRIA,
                    'orientamenti': [{'id': 0, 'trasformazione': []}]}
            geometria = stack.enter_context(patch('analisi.analizza', return_value=(object(), dati)))
            stack.enter_context(patch('augura_addon.step_in_stl'))
            stack.enter_context(patch('augura_addon.disponibile', return_value=True))
            stack.enter_context(patch('slicer_cli.disponibile', return_value=True))
            stack.enter_context(patch('classifica.applica'))
            nomi = ['slicer_cli.seziona_orientamenti', 'confronto.calcola', 'diagnostica.calcola',
                    'render.griglia_orientamenti', 'render.viste', 'augura_addon.verifica']
            mock = {nome: stack.enter_context(patch(nome)) for nome in nomi}
            mock['augura_addon.verifica'].return_value = {}
            lavorazioni.esegui(cartella, 'completa')
            stato = json.loads((cartella / 'lavorazione.json').read_text())
            self.assertEqual(stato['stato'], 'completata', stato)
            self.assertEqual(geometria.call_args.kwargs['cerca_orientamenti'],
                             scelte.get('analisi_orientamenti', True))
            return {nome: m.call_count for nome, m in mock.items()}

    def test_worker_trasmette_scelta_orientamenti(self):
        self.esegui({'analisi_orientamenti': False})

    def test_solo_orientamento_file_non_cerca_pose_ne_scelte_slicer(self):
        mesh = trimesh.creation.box(extents=[10, 20, 30])
        mesh.apply_transform(trimesh.transformations.rotation_matrix(.3, [1, 0, 0]))
        mesh.apply_translation([12, -8, 4])
        with tempfile.TemporaryDirectory() as tmp:
            percorso = Path(tmp) / 'pezzo.stl'
            mesh.export(percorso)
            with (patch.object(trimesh.Trimesh, 'compute_stable_poses', side_effect=AssertionError('pose')),
                 patch('orienta_slicer.scelta_slicer', side_effect=AssertionError('slicer')),
                  patch('orienta_slicer.costo', side_effect=AssertionError('costo'))):
                _, dati = analisi.analizza(percorso, cerca_orientamenti=False)
            self.assertFalse(dati['ricerca_orientamenti'])
            self.assertNotIn('confronto_slicer', dati)
            self.assertEqual(len(dati['orientamenti']), 1)
            o = dati['orientamenti'][0]
            self.assertEqual(o['origine'], 'come nel file')
            np.testing.assert_array_equal(o['trasformazione'], np.eye(4))
            self.assertAlmostEqual(o['altezza_mm'], mesh.extents[2], places=1)

    def test_augura_senza_ricerca_analizza_solo_file(self):
        with patch('augura_addon._json', return_value={'findings': []}) as richiesta:
            import augura_addon
            dati = augura_addon.verifica('pezzo.step', cerca_orientamenti=False)
        self.assertEqual(richiesta.call_count, 1)
        self.assertNotIn('orientamenti', dati)

    def test_sola_geometria_esclude_tutte_le_fasi_opzionali(self):
        chiamate = self.esegui({f'analisi_{fase}': False for fase in
                               ('slicing', 'varianti', 'controlli', 'immagini', 'step')})
        self.assertFalse(any(chiamate.values()), chiamate)

    def test_slicing_senza_varianti(self):
        chiamate = self.esegui({'analisi_varianti': False, 'analisi_controlli': False,
                               'analisi_immagini': False, 'analisi_step': False})
        self.assertEqual(chiamate['slicer_cli.seziona_orientamenti'], 1)
        self.assertEqual(chiamate['confronto.calcola'], 0)

    def test_varianti_richiedono_slicing(self):
        chiamate = self.esegui({'analisi_slicing': False})
        self.assertEqual(chiamate['confronto.calcola'], 0)
        self.assertEqual(chiamate['diagnostica.calcola'], 1)

    def test_vecchie_richieste_mantengono_analisi_completa(self):
        chiamate = self.esegui({})
        for nome in ('confronto.calcola', 'diagnostica.calcola',
                     'render.griglia_orientamenti', 'render.viste', 'augura_addon.verifica'):
            self.assertEqual(chiamate[nome], 1, nome)
