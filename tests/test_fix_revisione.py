import copy
import json
import tempfile
import unittest
import contextlib
import io
from pathlib import Path
from unittest.mock import patch

import numpy as np
import trimesh

import bobine
import calibrazione
import classifica
import confronto
import lavorazioni
import ottimizzazione
import slicer_cli
from persistenza import salva_json
import persistenza
import config


GCODE = ('; model printing time: 1m\n; filament used [g] = 1.5\n'
         '; total layer number: 5\n;TYPE:Outer wall\nG1 X1 Y1 E100\n; CONFIG_BLOCK_END\n')


class CacheTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.exe = self.root / 'slicer.exe'
        self.exe.write_bytes(b'slicer v1')
        self.stl = self.root / 'pezzo.stl'
        trimesh.creation.box().export(self.stl)
        self.fil = {'filament_density': ['1.25'], 'filament_diameter': ['1.75']}
        self.m, self.p = {'stampante': 'A'}, {'layer_height': '0.16'}
        self.patcher = patch.object(slicer_cli, 'ESEGUIBILE', self.exe)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def chiave(self):
        return slicer_cli.contesto(self.stl, self.m, self.p, self.fil)

    def test_cambia_per_ogni_input_e_versione_slicer(self):
        iniziale = self.chiave()
        for target, key, value in [(self.m, 'stampante', 'B'), (self.p, 'layer_height', '0.20'),
                                   (self.fil, 'filament_density', ['1.3'])]:
            prima = copy.deepcopy(target)
            target[key] = value
            self.assertNotEqual(iniziale, self.chiave())
            target.clear()
            target.update(prima)
        self.stl.write_bytes(b'altra geometria')
        self.assertNotEqual(iniziale, self.chiave())
        nuova = self.chiave()
        self.exe.write_bytes(b'slicer v2 piu lungo')
        self.assertNotEqual(nuova, self.chiave())

    def test_riuso_integrita_e_rifiuto_gcode_incompleto(self):
        out = self.root / 'calcolo'
        def esegui(*args, **kwargs):
            (out / 'plate_1.gcode').write_text(GCODE)
            return type('Esito', (), {'returncode': 0, 'stdout': '', 'stderr': ''})()
        with patch.object(slicer_cli.subprocess, 'run', side_effect=esegui) as run:
            primo = slicer_cli.seziona(self.stl, self.m, self.p, self.fil, out)
            secondo = slicer_cli.seziona(self.stl, self.m, self.p, self.fil, out)
            self.assertEqual(primo, secondo)
            self.assertEqual(run.call_count, 1)
            self.fil['temperatura'] = 240
            slicer_cli.seziona(self.stl, self.m, self.p, self.fil, out)
            self.assertEqual(run.call_count, 2)
            (out / 'plate_1.gcode').write_text(GCODE[:-30])
            slicer_cli.seziona(self.stl, self.m, self.p, self.fil, out)
            self.assertEqual(run.call_count, 3)
        (out / 'plate_1.gcode').write_text('; model printing time: 1m\nG1 X1 E100')
        with self.assertRaises(ValueError):
            slicer_cli.risultato_gcode(out / 'plate_1.gcode', self.fil)

    def test_cache_3mf_rifiuta_preset_o_file_cambiato(self):
        progetto = self.root / 'progetto.3mf'
        progetto.write_bytes(b'contenuto')
        chiave = self.chiave()
        slicer_cli.salva_cache(self.root, chiave, progetto, progetto.name + '.json')
        self.assertTrue(slicer_cli.cache_valida(self.root, chiave, progetto.name + '.json', progetto))
        self.p['wall_loops'] = '5'
        self.assertFalse(slicer_cli.cache_valida(self.root, self.chiave(), progetto.name + '.json', progetto))
        progetto.write_bytes(b'file danneggiato')
        self.assertFalse(slicer_cli.cache_valida(self.root, chiave, progetto.name + '.json', progetto))

    def test_fallimento_riprovabile_e_risultato_valido_riutilizzato(self):
        out = self.root / 'retry'
        esito_fallito = type('Esito', (), {'returncode': 1, 'stdout': '', 'stderr': 'errore'})()
        esito_valido = type('Esito', (), {'returncode': 0, 'stdout': '', 'stderr': ''})()
        tentativi = []
        def esegui(*args, **kwargs):
            tentativi.append(1)
            if len(tentativi) == 1:
                return esito_fallito
            (out / 'plate_1.gcode').write_text(GCODE)
            return esito_valido
        with patch.object(slicer_cli.subprocess, 'run', side_effect=esegui):
            with self.assertRaises(RuntimeError):
                slicer_cli.seziona(self.stl, self.m, self.p, self.fil, out)
            slicer_cli.seziona(self.stl, self.m, self.p, self.fil, out)
            slicer_cli.seziona(self.stl, self.m, self.p, self.fil, out)
        self.assertEqual(len(tentativi), 2)

    def test_scrittura_atomica_riprova_un_lock_transitorio_windows(self):
        originale = persistenza.os.replace
        tentativi = []
        def sostituisci(*args):
            tentativi.append(1)
            if len(tentativi) == 1:
                raise PermissionError('Lettore concorrente')
            return originale(*args)
        with patch.object(persistenza.os, 'replace', side_effect=sostituisci):
            salva_json(self.root / 'stato.json', {'stato': 'completata'})
        self.assertEqual(json.loads((self.root / 'stato.json').read_text())['stato'], 'completata')
        self.assertEqual(list(self.root.glob('*.tmp')), [])


class DatiTest(unittest.TestCase):
    def test_dashboard_bobine_omonime_tendenze_e_misura_vuota(self):
        from streamlit.testing.v1 import AppTest
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            diario = root / 'diario.jsonl'
            diario.write_text(json.dumps({'data': '2026-11-03', 'pezzo': 'Prova', 'materiale': 'PLA',
                                          'esito': 'buona', 'profilo_filamento': 'PLA prova'}) + '\n')
            elenco = [{'id': i, 'nome': 'Uguale', 'materiale': 'PLA', 'peso_netto_g': 1000,
                       'residuo_g': 100, 'stato': 'pronta'} for i in ('uno', 'due')]
            salva_json(root / 'bobine.json', elenco)
            with patch.multiple(config, LAVORI=root / 'lavori', FOTO=root / 'foto',
                                DIARIO=diario, BOBINE=root / 'bobine.json'):
                app = AppTest.from_file(str(config.CARTELLA / 'app.py'), default_timeout=30).run()
                self.assertFalse(app.exception)
                from tests.test_ui import vai_pagina
                vai_pagina(app, 'Bobine')
                self.assertEqual(len(app.selectbox(key='bobina_consumo').options), 2)
                vai_pagina(app, 'Diario')
                campo = next(n for n in app.number_input if n.label.startswith('Errore dimensionale'))
                self.assertIsNone(campo.value)
                self.assertEqual(app.selectbox(key='materiale_tendenze').value, 'PLA')

    def test_dimensioni_zero_e_dati_assenti(self):
        voci = [{'errore_dimensionale_mm': x} for x in (0, 0, 1, 1, None)]
        self.assertEqual(calibrazione.analizza(voci)['compensazione_dimensionale']['errore_mediano_mm'], .5)

    def test_calibrazione_separa_profilo_e_successi(self):
        voci = [
            {'materiale': 'PLA', 'profilo_filamento': 'A', 'esito': 'buona', 'temperatura_ugello_c': 210},
            {'materiale': 'PLA', 'profilo_filamento': 'A', 'esito': 'fallita', 'temperatura_ugello_c': 240},
            {'materiale': 'PLA', 'profilo_filamento': 'B', 'esito': 'ottima', 'temperatura_ugello_c': 180}]
        esito = calibrazione.analizza(voci, 'PLA', profilo='A')
        self.assertEqual(esito['mediane_registrate']['temperatura ugello °C'], 210)
        self.assertEqual(esito['stampe_considerate'], 2)

    def test_bobine_materiale_stato_e_riserva(self):
        voce = {'id': 'a', 'nome': 'PLA', 'materiale': 'PLA', 'peso_netto_g': 1000,
                'residuo_g': 103, 'stato': 'pronta', 'costo_eur': 20}
        self.assertEqual(bobine.stime([voce], None, 100), [])
        self.assertEqual(bobine.stime([voce], 'PETG', 100), [])
        self.assertFalse(bobine.stime([voce], 'PLA', 100)[0]['sufficiente'])
        voce['stato'] = 'da essiccare'
        self.assertEqual(bobine.stime([voce], 'PLA', 100), [])

    def test_rifiuta_tempi_invalidi_e_non_finiti(self):
        for tempo in (0, -1, None, float('nan'), float('inf')):
            r = {'tempo_s': tempo, 'materiale_g': 2, 'pezzo_g': 1, 'supporti_g': 0, 'brim_g': 1}
            self.assertIsNone(ottimizzazione.scegli([r], 'velocita'))
            self.assertFalse(classifica.calcola_punteggio_reale({'slicer': r}))

    def test_meccanica_blocca_profilo_insufficiente(self):
        r = {'orientamento_id': 1, 'variante_id': 'robusto', 'variante': 'Robusto',
             'posizione_orientamento': 1, 'tempo_s': 60, 'materiale_g': 2,
             'layer_height': '0.16', 'wall_loops': '3', 'sparse_infill_density': '25%'}
        opt = {'risultati': [r]}
        mec = {'orientamento_consigliato': 2, 'pareti_consigliate': 5}
        ottimizzazione.aggiorna_priorita(opt, 'robustezza e rigidità', mec)
        self.assertIsNone(opt['raccomandazione'])
        r.update(orientamento_id=2, wall_loops='5', variante_id='meccanico')
        ottimizzazione.aggiorna_priorita(opt, 'robustezza e rigidità', mec)
        self.assertEqual(opt['raccomandazione']['orientamento_id'], 2)

    def test_worker_errore_visibile_e_checkpoint_conservato(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            salva_json(p / 'richiesta.json', {})
            checkpoint = {'file': str(p / 'mancante.stl'), 'orientamenti': []}
            salva_json(p / 'analisi.json', checkpoint)
            with contextlib.redirect_stderr(io.StringIO()):
                lavorazioni.esegui(p, 'varianti')
            self.assertEqual(lavorazioni.stato(p)['stato'], 'errore')
            self.assertEqual(json.loads((p / 'analisi.json').read_text()), checkpoint)


if __name__ == '__main__':
    unittest.main()
