import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import trimesh

from streamlit.testing.v1 import AppTest
import config
import classifica
import confronto
import ottimizzazione
import slicer_cli
from persistenza import salva_json


class EsportazioneSceltaTest(unittest.TestCase):
    def test_scelta_manual_json_stl_3mf_e_persistenza_durante_il_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = root/'lavori'/'prova'
            p.mkdir(parents=True)
            trimesh.creation.box(extents=[10,8,6]).export(p/'pezzo.stl')
            d = {'file': str(p/'pezzo.stl'), 'versione_geometria':config.VERSIONE_GEOMETRIA,
                 'dimensioni_mm':[10,8,6], 'volume_cm3':.48, 'chiuso_stagno':True,
                 'spessori':{'minimo_mm':6, 'area_sotto_1_2mm_pct':0},
                 'sezionamento':{'processo':config.PROFILO_PROCESSO, 'filamento':config.PROFILO_FILAMENTO,
                                 'supporti':config.SUPPORTI_SEZIONAMENTO},
                 'orientamenti':[{'id':oid, 'origine':'posa stabile', 'trasformazione':np.eye(4).tolist(),
                                  'punteggio':0, 'slicer':{'tempo':'1m', 'tempo_s':60, 'pezzo_g':1,
                                                         'supporti_g':0, 'brim_g':0}} for oid in (3,2)]}
            classifica.applica(d)
            varianti = copy.deepcopy(config.VARIANTI_PROCESSO)
            extra = []
            for o in d['orientamenti'][:2]:
                for i, v in enumerate(varianti):
                    if v.get('riferimento'): continue
                    r = {'tempo_s': 60+i, 'tempo': f'{60+i}s', 'pezzo_g': 10,
                         'supporti_g': 0, 'brim_g': 0, 'strati': 20, 'consumo_totale_g': 11}
                    extra.append({'orientamento_id': o['id'], 'variante_id': v['id'], 'risultato': r})
                    sotto = p/'varianti'/f"orientamento_{o['id']}"/v['id']
                    sotto.mkdir(parents=True)
                    (sotto/'pezzo.stl').write_bytes((p/'pezzo.stl').read_bytes())
            richiesta = { 'priorita': 'velocità di stampa', 'budget_ricerca': 0 }
            opt = ottimizzazione.costruisci(d['orientamenti'], varianti, extra, richiesta['priorita'])
            opt['firma'] = confronto.firma(p/'pezzo.stl', d, richiesta)
            d['ottimizzazione_processo'] = opt
            salva_json(p/'analisi.json', d)
            salva_json(p/'richiesta.json', richiesta)
            with patch.multiple(config, LAVORI=root/'lavori', FOTO=root/'foto',
                                DIARIO=root/'diario.jsonl', BOBINE=root/'bobine.json'), \
                 patch.object(slicer_cli, 'profilo_utente', wraps=slicer_cli.profilo_utente) as profilo, \
                 patch('lavorazioni.avvia') as avvia:
                app = AppTest.from_file(str(config.CARTELLA/'app.py'), default_timeout=60)
                app.query_params['lavoro'] = p.name
                app.run()
                self.assertFalse(app.exception)
                selettore = next(x for x in app.selectbox if x.label == 'Configurazione da esportare')
                self.assertEqual(selettore.value, (opt['raccomandazione']['orientamento_id'], opt['raccomandazione']['variante_id']))
                scelta = (d['orientamenti'][1]['id'], 'veloce')
                selettore.select(scelta).run()
                self.assertFalse(app.exception)
                self.assertEqual(profilo.call_args.args[2]['layer_height'], '0.24')
                self.assertTrue(any(b.label == f'Scarica STL orientamento {scelta[0]}' for b in app.get('download_button')))
                next(b for b in app.button if b.label == 'Prepara progetto 3MF').click().run()
                avvia.assert_called_with(p, '3mf')
                spec = json.loads((p/'esportazione.json').read_text(encoding='utf-8'))
                self.assertEqual(spec['modifiche']['layer_height'], '0.24')
                self.assertIn(f'orientamento_{scelta[0]}', spec['stl'])
                self.assertIn('veloce', spec['destinazione'])
                # Il menu scompare durante il worker, poi deve ricomparire sulla stessa scelta manuale.
                salva_json(p/'lavorazione.json', {'stato':'in corso', 'pid':os.getpid(), 'frazione':.1})
                app.run()
                self.assertFalse(any(x.label == 'Configurazione da esportare' for x in app.selectbox))
                salva_json(p/'lavorazione.json', {'stato':'completata'})
                app.run()
                selettore = next(x for x in app.selectbox if x.label == 'Configurazione da esportare')
                self.assertEqual(selettore.value, scelta)


if __name__ == '__main__':
    unittest.main()
