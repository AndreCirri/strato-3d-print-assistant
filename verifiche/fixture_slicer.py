"""Profili sintetici per i test: non richiede né esegue ElegooSlicer."""
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import config
import slicer_cli
from persistenza import salva_json


@contextmanager
def slicer_fittizio(cartella):
    root = Path(cartella) / 'slicer_fixture'
    profili = root / 'resources' / 'profiles' / 'Elegoo'
    profili.mkdir(parents=True, exist_ok=True)
    exe = root / 'slicer-stub.exe'
    exe.write_bytes(b'Test fixture: not an executable')
    for nome, dati in (
        (config.PROFILO_STAMPANTE, {'type': 'machine'}),
        (config.PROFILO_FILAMENTO, {'type': 'filament', 'filament_density': ['1.25'], 'filament_diameter': ['1.75']}),
        ('Processo base fixture', {'type': 'process', 'layer_height': '0.16', 'wall_loops': '2',
                                  'sparse_infill_density': '15%', 'setting_id': 'fixture', 'instantiation': 'false'}),
        (config.PROFILO_PROCESSO, {'type': 'process', 'inherits': 'Processo base fixture'}),
    ):
        salva_json(profili / (str(len(list(profili.glob('*.json')))) + '.json'),
                   {'name': nome, 'instantiation': 'true', **dati})
    with patch.object(slicer_cli, 'ESEGUIBILE', exe), patch.object(slicer_cli, 'PROFILI', profili):
        yield
