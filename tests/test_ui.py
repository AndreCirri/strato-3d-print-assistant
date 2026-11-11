"""Verifica il percorso guidato e la persistenza tra widget non montati."""
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
import trimesh
import config
import diario
from persistenza import salva_json


def vai_pagina(app, titolo):
    # AppTest.switch_page supporta solo file, mentre queste pagine usano callable.
    app._page_hash = next(p.proto.page_script_hash for p in app.get('page_link')
                          if p.proto.label == titolo)
    return app.run()


class PercorsoUiTest(unittest.TestCase):
    def test_ogni_pagina_monta_solo_la_propria_sezione(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.multiple(config, LAVORI=Path(tmp) / 'lavori', FOTO=Path(tmp) / 'foto',
                            DIARIO=Path(tmp) / 'diario.jsonl', BOBINE=Path(tmp) / 'bobine.json'), \
             patch('slicer_cli.disponibile', return_value=False), \
             patch('augura_addon.disponibile', return_value=False):
            app = AppTest.from_file(str(config.CARTELLA / 'app.py')).run()
            for titolo, widget in [('Diario', 'text_area'), ('Bobine', 'text_input'),
                                   ('Storico', 'button'), ('Impostazioni', 'selectbox')]:
                vai_pagina(app, titolo)
                self.assertFalse(app.exception)
                self.assertFalse(any(w.key == 'upload_ui' for w in app.get('file_uploader')))
                self.assertTrue(getattr(app, widget))
            vai_pagina(app, 'Analisi')
            self.assertTrue(app.get('file_uploader'))
            self.assertFalse(any(w.key == 'provider_ai' for w in app.selectbox))
            self.assertFalse(app.tabs)

    def test_storico_non_mostra_un_upload_diverso_dal_lavoro_riaperto(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.multiple(config, LAVORI=Path(tmp) / 'lavori', FOTO=Path(tmp) / 'foto',
                            DIARIO=Path(tmp) / 'diario.jsonl', BOBINE=Path(tmp) / 'bobine.json'), \
             patch('slicer_cli.disponibile', return_value=False), \
             patch('augura_addon.disponibile', return_value=False), \
             patch('lavorazioni.avvia') as avvia:
            cartella = config.LAVORI / 'storico_B'
            cartella.mkdir(parents=True)
            trimesh.creation.box(extents=[20, 10, 5]).export(cartella / 'B.stl')
            salva_json(cartella / 'analisi.json', {
                'file': str(cartella / 'B.stl'), 'versione_geometria': config.VERSIONE_GEOMETRIA,
                'dimensioni_mm': [20, 10, 5], 'volume_cm3': 1, 'chiuso_stagno': True,
                'spessori': {'minimo_mm': 5, 'area_sotto_1_2mm_pct': 0},
                'orientamenti': [{'id': 1, 'origine': 'posa stabile', 'punteggio': 0,
                    'trasformazione': trimesh.transformations.identity_matrix().tolist()}]})
            salva_json(cartella / 'richiesta.json', {'scopo': 'Scopo di B'})
            salva_json(cartella / 'ingresso.json', {'file': 'B.stl'})
            modello = io.BytesIO(trimesh.creation.box().export(file_type='stl'))
            modello.name = 'A.stl'
            app = AppTest.from_file(str(config.CARTELLA / 'app.py'), default_timeout=60)
            app.session_state['modello_ui'] = modello
            vai_pagina(app.run(), 'Storico').button(key='apristorico_B').click().run()
            self.assertFalse(app.exception)
            self.assertIn('lavoro', app.query_params)
            self.assertEqual(app.session_state['scopo'], 'Scopo di B')
            self.assertNotIn('modello_ui', app.session_state)
            self.assertTrue(app.button(key='fase_2').disabled)
            ricaricata = AppTest.from_file(str(config.CARTELLA / 'app.py'), default_timeout=60)
            ricaricata.query_params['lavoro'] = cartella.name
            ricaricata.run()
            self.assertFalse(ricaricata.exception)
            self.assertEqual(ricaricata.session_state['lavoro'], str(cartella))
            self.assertEqual(ricaricata.session_state['scopo'], 'Scopo di B')
            self.assertEqual(ricaricata.session_state['fase_ui'], 6)
            avvia.assert_not_called()

    def test_diagnosi_diario_usa_il_modello_ai_e_parte_solo_su_richiesta(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.multiple(config, LAVORI=Path(tmp) / 'lavori', FOTO=Path(tmp) / 'foto',
                            DIARIO=Path(tmp) / 'diario.jsonl', BOBINE=Path(tmp) / 'bobine.json'), \
             patch('slicer_cli.disponibile', return_value=False), \
             patch('augura_addon.disponibile', return_value=False), \
             patch('diario_ui.chiedi', return_value=('Prova migliore', 0, None)) as chiedi:
            diario.aggiungi({'pezzo': 'Staffa', 'esito': 'buona', 'materiale': 'PLA'})
            app = AppTest.from_file(str(config.CARTELLA / 'app.py'), default_timeout=60).run()
            self.assertFalse(app.exception)
            chiedi.assert_not_called()
            vai_pagina(app, 'Diario')
            app.button(key='diag0').click().run()
            self.assertFalse(app.exception)
            chiedi.assert_called_once()
            self.assertIsInstance(chiedi.call_args.args[2], str)
            self.assertEqual(diario.tutte()[0]['diagnosi'], 'Prova migliore')

    def test_avvio_dal_riepilogo_crea_il_lavoro_e_avvia_il_worker(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.multiple(config, LAVORI=Path(tmp) / 'lavori', FOTO=Path(tmp) / 'foto',
                            DIARIO=Path(tmp) / 'diario.jsonl', BOBINE=Path(tmp) / 'bobine.json'), \
             patch('slicer_cli.disponibile', return_value=False), \
             patch('augura_addon.disponibile', return_value=False), \
             patch('lavorazioni.avvia') as avvia:
            modello = io.BytesIO(trimesh.creation.box().export(file_type='stl'))
            modello.name = 'avvio.stl'
            app = AppTest.from_file(str(config.CARTELLA / 'app.py'), default_timeout=60)
            app.session_state['modello_ui'] = modello
            app.session_state['fase_ui'] = 4
            app.run()
            next(b for b in app.button if b.label == 'Avvia analisi →').click().run()
            self.assertFalse(app.exception)
            avvia.assert_called_once()
            cartella = avvia.call_args.args[0]
            self.assertIn('lavoro', app.query_params)
            self.assertTrue((cartella / 'ingresso.json').is_file())
            self.assertEqual((cartella / modello.name).read_bytes(), modello.getvalue())

    def test_scelta_codex_e_ritorno_a_claude(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(config, 'LAVORI', Path(tmp) / 'lavori'), \
             patch.object(config, 'FOTO', Path(tmp) / 'foto'), \
             patch('slicer_cli.disponibile', return_value=False), \
             patch('augura_addon.disponibile', return_value=False):
            app = AppTest.from_file(str(config.CARTELLA / 'app.py'), default_timeout=30).run()
            self.assertFalse(app.exception)
            vai_pagina(app, 'Impostazioni')
            app.selectbox(key='provider_ai').select('Codex').run()
            self.assertFalse(app.exception)
            self.assertEqual(app.selectbox(key='modello_codex').value, '')
            for modello in ('gpt-6.1-sol', 'gpt-6.1-terra', 'gpt-6-luna', 'gpt-6-astra', 'gpt-6-sol'):
                app.selectbox(key='modello_codex').select(modello).run()
                self.assertFalse(app.exception)
                self.assertEqual(app.selectbox(key='modello_codex').value, modello)
            app.selectbox(key='modello_codex').select('').run()
            self.assertEqual(app.selectbox(key='modello_codex').value, '')
            vai_pagina(app, 'Diario')
            self.assertFalse(any(w.key == 'provider_ai' for w in app.selectbox))
            vai_pagina(app, 'Impostazioni')
            self.assertEqual(app.selectbox(key='provider_ai').value, 'Codex')
            self.assertEqual(app.selectbox(key='modello_codex').value, '')
            app.selectbox(key='provider_ai').select('Claude').run()
            self.assertFalse(app.exception)
            self.assertTrue(any(w.label == 'Modello di Claude' for w in app.selectbox))

    def test_percorso_conserva_contesto_e_blocca_avvio_senza_file(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(config, 'LAVORI', Path(tmp) / 'lavori'), \
             patch.object(config, 'FOTO', Path(tmp) / 'foto'), \
             patch('slicer_cli.disponibile', return_value=False), \
             patch('augura_addon.disponibile', return_value=False):
            app = AppTest.from_file(str(config.CARTELLA / 'app.py'), default_timeout=30).run()
            self.assertFalse(app.exception)
            self.assertTrue(app.button(key='fase_2').disabled)
            self.assertFalse(any(b.key == 'percorso_indietro' for b in app.button))
            modello = io.BytesIO(trimesh.creation.box().export(file_type='stl'))
            modello.name = 'esempio.stl'
            app.session_state['modello_ui'] = modello
            app.run()
            self.assertEqual(len(app.get('plotly_chart')), 1)
            self.assertTrue(app.button(key='rimuovi_modello'))
            app.button(key='fase_2').click().run()
            self.assertFalse(app.button(key='percorso_indietro').disabled)
            app.text_area(key='scopo').set_value('Staffa del motore').run()
            app.button(key='fase_3').click().run()
            app.radio(key='priorita').set_value('poco materiale').run()
            app.button(key='fase_4').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state['scopo'], 'Staffa del motore')
            self.assertEqual(app.session_state['priorita'], 'poco materiale')
            app.button(key='fase_2').click().run()
            self.assertEqual(app.text_area(key='scopo').value, 'Staffa del motore')
            self.assertFalse(app.exception)
            app.button(key='fase_1').click().run()
            self.assertFalse(any(b.key == 'percorso_indietro' for b in app.button))
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
