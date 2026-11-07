"""Verifica il percorso guidato e la persistenza tra widget non montati."""
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
import trimesh
import config


class PercorsoUiTest(unittest.TestCase):
    def test_percorso_conserva_contesto_e_blocca_avvio_senza_file(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(config, 'LAVORI', Path(tmp) / 'lavori'), \
             patch.object(config, 'FOTO', Path(tmp) / 'foto'), \
             patch('slicer_cli.disponibile', return_value=False), \
             patch('augura_addon.disponibile', return_value=False):
            app = AppTest.from_file(str(config.CARTELLA / 'app.py'), default_timeout=30).run()
            self.assertFalse(app.exception)
            self.assertTrue(app.button(key='fase_2').disabled)
            modello = io.BytesIO(trimesh.creation.box().export(file_type='stl'))
            modello.name = 'esempio.stl'
            app.session_state['modello_ui'] = modello
            app.run()
            self.assertEqual(len(app.get('plotly_chart')), 1)
            self.assertTrue(app.button(key='rimuovi_modello'))
            app.button(key='fase_2').click().run()
            app.text_area(key='scopo').set_value('Staffa del motore').run()
            app.button(key='fase_3').click().run()
            app.selectbox(key='priorita').select('poco materiale').run()
            app.button(key='fase_4').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state['scopo'], 'Staffa del motore')
            self.assertEqual(app.session_state['priorita'], 'poco materiale')
            app.button(key='fase_2').click().run()
            self.assertEqual(app.text_area(key='scopo').value, 'Staffa del motore')
            self.assertFalse(app.exception)
            app.button(key='fase_1').click().run()
            self.assertEqual(len(app.get('plotly_chart')), 1)
            app.button(key='rimuovi_modello').click().run()
            self.assertIsNone(app.session_state['modello_ui'])
            self.assertFalse(app.get('image'))
            self.assertFalse(app.get('plotly_chart'))
            self.assertTrue(app.button(key='fase_2').disabled)
            self.assertEqual(app.get('file_uploader')[0].key, 'upload_ui')
            self.assertFalse(app.exception)


if __name__ == '__main__':
    unittest.main()
