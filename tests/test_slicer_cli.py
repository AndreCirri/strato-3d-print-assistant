import unittest
import tempfile
from pathlib import Path

import slicer_cli
import config
from tests.fixture_slicer import slicer_fittizio


class ProfiloUtenteTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        fixture = slicer_fittizio(tmp.name)
        fixture.__enter__()
        self.addCleanup(fixture.__exit__, None, None, None)

    def test_crea_un_profilo_importabile_con_le_modifiche_usate_dallo_slicer(self):
        profilo = slicer_cli.profilo_utente(
            "Assistente stampa - Veloce",
            "0.16mm Optimal @Elegoo CC 0.4 nozzle",
            {"layer_height": "0.24", "wall_loops": "2", "sparse_infill_density": "10%"},
            {"enable_support": "1", "support_type": "tree(auto)"},
        )

        self.assertEqual(profilo["type"], "process")
        self.assertEqual(profilo["from"], "User")
        self.assertNotIn("inherits", profilo)
        self.assertEqual(profilo["name"], profilo["print_settings_id"])
        self.assertEqual(profilo["layer_height"], "0.24")
        self.assertEqual(profilo["support_type"], "tree(auto)")

    def test_percorsi_personalizzati_e_profili_derivati_dalleseguibile(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / 'Slicer personalizzato' / 'slicer.exe'
            eseguibile, profili = config.percorsi_slicer({'STRATO_SLICER_EXE': str(exe)})
            self.assertEqual(eseguibile, exe)
            self.assertEqual(profili, exe.parent / 'resources' / 'profiles' / 'Elegoo')
            _, profili = config.percorsi_slicer({'STRATO_SLICER_EXE': str(exe),
                                               'STRATO_SLICER_PROFILES': str(Path(tmp) / 'profili')})
            self.assertEqual(profili, Path(tmp) / 'profili')

    def test_percorsi_relativi_partono_dal_progetto(self):
        exe, profili = config.percorsi_slicer({'STRATO_SLICER_EXE': 'strumenti/slicer.exe',
                                              'STRATO_SLICER_PROFILES': 'strumenti/profili'})
        self.assertEqual(exe, config.CARTELLA / 'strumenti' / 'slicer.exe')
        self.assertEqual(profili, config.CARTELLA / 'strumenti' / 'profili')


if __name__ == "__main__":
    unittest.main()
