import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import config
from avanzamento import Avanzamento


class AvanzamentoTest(unittest.TestCase):
    def test_persistenza_contatori_monotonia_e_completamento(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            a = Avanzamento(p, 'varianti')
            a.aggiorna('Orientamento 2', .3, 2, 6)
            stato = json.loads((p / 'lavorazione.json').read_text())
            self.assertEqual((stato['completati'], stato['totale']), (2,6))
            a.aggiorna('Ricerca', .1, 0, 4)
            self.assertEqual(json.loads((p / 'lavorazione.json').read_text())['frazione'], .3)
            a.aggiorna('Salvataggio', 1.)
            self.assertEqual(json.loads((p / 'lavorazione.json').read_text())['frazione'], .99)
            a.termina()
            stato = json.loads((p / 'lavorazione.json').read_text())
            self.assertEqual(stato['frazione'], 1.)
            self.assertEqual(stato['stato'], 'completata')

    def test_errore_non_diventa_cento_percento(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            a = Avanzamento(p, 'completa')
            a.aggiorna('Sezionamento', .4)
            a.termina(ValueError('Slicer interrotto'))
            stato = json.loads((p / 'lavorazione.json').read_text())
            self.assertEqual(stato['stato'], 'errore')
            self.assertEqual(stato['frazione'], .4)

    def test_dashboard_mostra_avanzamento_e_link_alle_pagine(self):
        from streamlit.testing.v1 import AppTest
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lavoro = root / 'lavori' / 'prova'
            lavoro.mkdir(parents=True)
            Avanzamento(lavoro, 'varianti').aggiorna('Varianti — Veloce', .45, 3, 8)
            with patch.multiple(config, LAVORI=root/'lavori', FOTO=root/'foto',
                                DIARIO=root/'diario.jsonl', BOBINE=root/'bobine.json'):
                app = AppTest.from_file(str(config.CARTELLA/'app.py'), default_timeout=60)
                app.session_state['lavoro'] = str(lavoro)
                app.run()
                self.assertFalse(app.exception)
                self.assertEqual([link.proto.label for link in app.get('page_link')],
                             ["Analisi", "Diario", "Bobine", "Storico", "Impostazioni"])
                barre = app.get('progress')
                self.assertEqual(len(barre), 1)
                self.assertIn('45%', barre[0].proto.text)
                self.assertIn('3 di 8', barre[0].proto.text)


if __name__ == '__main__':
    unittest.main()
