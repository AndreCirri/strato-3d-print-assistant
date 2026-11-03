import unittest

import slicer_cli


class ProfiloUtenteTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
