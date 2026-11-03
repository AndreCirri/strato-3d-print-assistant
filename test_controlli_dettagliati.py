import tempfile
import unittest
from pathlib import Path
import trimesh
import sezioni
import toolpath


def blocco(dimensioni, centro):
    m = trimesh.creation.box(extents=dimensioni)
    m.apply_translation(centro)
    return m


class SezioniTest(unittest.TestCase):
    def test_cavita_chiusa_e_contenitore_aperto_distinti(self):
        esterno = blocco([10,10,10], [0,0,5])
        cavita = blocco([4,4,4], [0,0,5])
        chiuso = trimesh.boolean.difference([esterno,cavita], engine='manifold')
        aperto = trimesh.boolean.difference([esterno,blocco([8,8,10],[0,0,6])], engine='manifold')
        risultato = sezioni.analizza(chiuso)
        self.assertEqual(len(risultato['cavita_chiuse']), 1)
        self.assertEqual(sezioni.analizza(aperto)['cavita_chiuse'], [])
        supporti = {'centro_modello_xy': [100,100], 'punti_supporto': [[100,100,5]]}
        self.assertEqual(sezioni.analizza(chiuso, dati_toolpath=supporti)['campioni_supporto_in_cavita_chiuse'], 1)

    def test_cavita_aperta_ma_non_accessibile_a_utensile_2mm(self):
        esterno = blocco([10,10,10],[0,0,5])
        interno = trimesh.boolean.union([blocco([4,4,4],[0,0,3]),blocco([1,1,6],[0,0,7.5])],engine='manifold')
        m = trimesh.boolean.difference([esterno,interno],engine='manifold')
        risultato = sezioni.analizza(m)
        self.assertFalse(risultato['cavita_chiuse'])
        self.assertGreater(risultato['zone_inaccessibili_utensile_2mm'], 0)

    def test_luce_del_ponte_tra_due_appoggi(self):
        elementi = [blocco([2,6,6],[-5,0,3]), blocco([2,6,6],[5,0,3]), blocco([12,6,1],[0,0,6.5])]
        m = trimesh.boolean.union(elementi, engine='manifold')
        ponti = sezioni.analizza(m)['ponti']
        self.assertTrue(ponti)
        self.assertAlmostEqual(ponti[0]['luce_mm'], 8, delta=.2)

    def test_foro_stretto_e_isola_sospesa(self):
        esterno = blocco([10,10,5],[0,0,2.5])
        foro = trimesh.creation.cylinder(radius=.5, height=8, sections=32)
        foro.apply_translation([0,0,2.5])
        m = trimesh.boolean.difference([esterno,foro], engine='manifold')
        self.assertTrue(sezioni.analizza(m)['fori_piccoli'])
        isola = trimesh.util.concatenate([blocco([2,2,1],[0,0,.5]), blocco([2,2,1],[5,0,4])])
        self.assertTrue(sezioni.analizza(isola)['isole_geometriche'])


class ToolpathTest(unittest.TestCase):
    def analizza(self, testo):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'pezzo.gcode'
            p.write_text(testo)
            return toolpath.analizza(p)

    def test_collisione_e_viaggio_con_zhop(self):
        inizio = 'M83\n;TYPE:Outer wall\nG1 X0 Y0 Z0.2\nG1 X10 E1\n'
        self.assertTrue(self.analizza(inizio + 'G0 Z0.1\nG0 X0\n')['collisioni'])
        self.assertFalse(self.analizza(inizio + 'G0 Z0.6\nG0 X0\n')['collisioni'])

    def test_isola_reale_in_gcode_e_supporto_presente(self):
        testo = 'M83\n;TYPE:Outer wall\nG1 Z0.2\nG1 X10 E1\nG0 X30 Z0.4\nG1 X40 E1\n'
        self.assertTrue(self.analizza(testo)['isole_senza_appoggio'])
        valido = 'M83\n;TYPE:Support\nG1 Z0.2\nG1 X10 E1\n;TYPE:Outer wall\nG0 X0 Z0.4\nG1 X10 E1\n'
        self.assertFalse(self.analizza(valido)['isole_senza_appoggio'])

    def test_limiti_archi_non_supportati_espliciti(self):
        risultato = self.analizza('M83\n;TYPE:Outer wall\nG2 X10 Y0 R5 E1\n')
        self.assertEqual(risultato['archi_non_analizzati'], 1)

    def test_arco_ij_usa_il_percorso_curvo(self):
        risultato = self.analizza('M83\n;TYPE:Outer wall\nG1 X1 Y0 Z0.2\nG3 X-1 Y0 I-1 J0 E1\n')
        self.assertEqual(risultato['archi_non_analizzati'], 0)
        self.assertGreater(risultato['centro_modello_xy'][1], .4)

    def test_estrusione_assoluta_non_scambia_un_viaggio_per_materiale(self):
        risultato = self.analizza('M82\n;TYPE:Outer wall\nG1 Z0.2\nG1 X10 E1\nG0 X20 E1\n')
        self.assertAlmostEqual(risultato['centro_modello_xy'][0], 5)


if __name__ == '__main__':
    unittest.main()
