import unittest
import ricerca


def riga(oid=1, pareti='2'):
    return {'orientamento_id': oid, 'variante_id': 'base', 'variante': 'Base',
            'layer_height': '0.24', 'wall_loops': pareti, 'sparse_infill_density': '10%',
            'tempo_s': 60, 'materiale_g': 2, 'posizione_orientamento': 1}


class RicercaTest(unittest.TestCase):
    def test_cambia_un_solo_parametro_e_non_ripete_coppie(self):
        base = riga()
        oid, variante = ricerca.proponi([base], [], 'velocità di stampa')
        self.assertEqual(oid, 1)
        self.assertEqual(variante['impostazioni']['layer_height'], '0.28')
        self.assertEqual(sum(base[k] != variante['impostazioni'][k] for k in ricerca.LIMITI), 1)
        provata = {**base, **variante['impostazioni'], 'variante_id': variante['id']}
        altra = ricerca.proponi([base, provata], [variante], 'velocità di stampa')[1]
        self.assertNotEqual(altra['impostazioni'], variante['impostazioni'])

    def test_rispetta_pareti_e_orientamento_meccanico(self):
        meccanica = {'orientamento_consigliato': 2, 'pareti_consigliate': 5}
        self.assertIsNone(ricerca.proponi([riga()], [], 'robustezza e rigidità', meccanica))
        oid, variante = ricerca.proponi([riga(2, '5')], [], 'robustezza e rigidità', meccanica)
        self.assertEqual(oid, 2)
        self.assertGreaterEqual(int(variante['impostazioni']['wall_loops']), 5)


if __name__ == '__main__':
    unittest.main()
