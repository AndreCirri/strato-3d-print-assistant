"""Test Chromium separati dalla discovery unittest; nessun dato personale o slicer richiesto."""
import io
import json
import os
import re
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.request import urlopen

from PIL import Image, ImageColor
from playwright.sync_api import sync_playwright, expect
import trimesh

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'browser-results'
CHART = '.st-key-modello3d_caricamento .js-plotly-plot'
expect.set_options(timeout=45000)


class BrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        OUTPUT.mkdir(exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(prefix='strato_browser_')
        cls.addClassCleanup(cls.temporary.cleanup)
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        cls.url = f'http://127.0.0.1:{port}'
        cls.log = (OUTPUT / 'streamlit.log').open('w', encoding='utf-8')
        cls.addClassCleanup(cls.log.close)
        env = {**os.environ, 'STRATO_BROWSER_DATA': cls.temporary.name,
               'STRATO_SLICER_EXE': 'missing/slicer.exe', 'STRATO_SLICER_PROFILES': 'missing/profiles'}
        cls.server = subprocess.Popen(
            [sys.executable, '-m', 'streamlit', 'run', 'tests/browser_app.py',
             '--server.address', '127.0.0.1', '--server.port', str(port),
             '--server.headless', 'true', '--browser.gatherUsageStats', 'false'],
            cwd=ROOT, env=env, stdout=cls.log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        cls.addClassCleanup(cls.stop_server)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if cls.server.poll() is not None:
                raise RuntimeError('Streamlit exited; see browser-results/streamlit.log')
            try:
                with urlopen(cls.url + '/_stcore/health', timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(.2)
        else:
            raise RuntimeError('Streamlit startup timed out')
        print(f'Isolated Streamlit ready: {cls.url}', flush=True)
        cls.playwright = sync_playwright().start()
        cls.addClassCleanup(cls.playwright.stop)
        cls.browser = cls.playwright.chromium.launch(args=['--enable-unsafe-swiftshader'])
        cls.addClassCleanup(cls.browser.close)
        print('Chromium ready', flush=True)

    @classmethod
    def stop_server(cls):
        if cls.server.poll() is not None:
            return
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(cls.server.pid), '/T', '/F'],
                           capture_output=True, timeout=15)
            cls.server.wait(timeout=10)
            return
        cls.server.terminate()
        try:
            cls.server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            cls.server.kill()
            cls.server.wait(timeout=10)

    def setUp(self):
        self.context = self.browser.new_context(viewport={'width': 1366, 'height': 768})
        self.addCleanup(self.context.close)
        self.context.tracing.start(screenshots=True, snapshots=True, sources=True)
        self.page = self.context.new_page()
        self.page.set_default_timeout(45000)
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.addCleanup(self.save_evidence)
        self.page.goto(self.url)
        expect(self.page.get_by_role('heading', name='Carica il modello')).to_be_visible()
        self.ready()

    def save_evidence(self):
        try:
            self.page.screenshot(path=str(OUTPUT / f'{self._testMethodName}.png'), full_page=True)
            (OUTPUT / f'{self._testMethodName}-errors.json').write_text(
                json.dumps(self.errors, indent=2), encoding='utf-8')
        finally:
            self.context.tracing.stop(path=str(OUTPUT / f'{self._testMethodName}-trace.zip'))

    def tearDown(self):
        self.assertEqual(self.errors, [], 'Uncaught browser errors')
        expect(self.page.locator('[data-testid="stException"]')).to_have_count(0)

    def ready(self):
        self.page.wait_for_function("""() => document.querySelector(
            '[data-testid="stApp"][data-test-script-state="notRunning"]') !== null""")

    def button(self, key):
        locator = self.page.locator(f'.st-key-{key} button:visible')
        # Streamlit briefly retains stale widgets during a rerun.
        expect(locator).to_have_count(1)
        return locator

    def upload(self, filename='box.stl', mesh=None):
        mesh = mesh if mesh is not None else trimesh.creation.box(extents=[20, 10, 5])
        content = mesh.export(file_type=Path(filename).suffix[1:])
        if isinstance(content, str):
            content = content.encode()
        self.page.locator('.st-key-modello_box input[type=file]').set_input_files(
            {'name': filename, 'mimeType': 'application/octet-stream', 'buffer': content})
        expect(self.button('rimuovi_modello')).to_be_visible()
        self.viewer()
        self.ready()

    def viewer(self):
        self.page.wait_for_function("""selector => {
            const p = document.querySelector(selector);
            return p?.data?.some(t => t.type === 'mesh3d' && t.i.length > 0)
                && p._fullLayout?.scene?._scene?.glplot;
        }""", arg=CHART)
        expect(self.page.locator(CHART + ' canvas').first).to_be_visible()

    def visible_without_scroll(self, locator):
        expect(locator).to_be_visible()
        box = locator.bounding_box()
        viewport = self.page.viewport_size
        self.assertGreaterEqual(box['y'], 0)
        self.assertLessEqual(box['y'] + box['height'], viewport['height'])
        self.assertGreaterEqual(box['x'], 0)
        self.assertLessEqual(box['x'] + box['width'], viewport['width'])
        self.assertTrue(locator.evaluate("""el => {
            const r = el.getBoundingClientRect();
            return el.contains(document.elementFromPoint(r.x+r.width/2, r.y+r.height/2));
        }"""), 'Button covered by another element')

    def check_format(self, extension):
        self.upload(f'box.{extension}')
        expect(self.page.locator('.st-key-modello_box')).to_contain_text(f'box.{extension}')
        expect(self.page.locator('.st-key-modello_box input[type=file]')).to_have_count(0)
        self.button('rimuovi_modello').click()
        expect(self.page.locator('.st-key-modello_box input[type=file]')).to_have_count(1)

    def test_upload_stl(self):
        self.check_format('stl')

    def test_upload_obj(self):
        self.check_format('obj')

    def test_upload_3mf(self):
        self.check_format('3mf')

    def test_remove_reload_same_file_and_replace(self):
        self.upload()
        original = self.page.locator(CHART).evaluate('p => p.layout.uirevision')
        self.button('rimuovi_modello').click()
        expect(self.page.locator(CHART)).to_have_count(0)
        expect(self.button('percorso_avanti')).to_be_disabled()
        self.upload()
        self.assertEqual(self.page.locator(CHART).evaluate('p => p.layout.uirevision'), original)
        self.button('rimuovi_modello').click()
        self.upload('sphere.stl', trimesh.creation.icosphere(subdivisions=1))
        self.assertNotEqual(self.page.locator(CHART).evaluate('p => p.layout.uirevision'), original)

    def test_invalid_model_can_be_removed(self):
        self.page.locator('.st-key-modello_box input[type=file]').set_input_files(
            {'name': 'invalid.stl', 'mimeType': 'application/octet-stream', 'buffer': b'not a model'})
        expect(self.page.get_by_text('Anteprima non disponibile.', exact=False)).to_be_visible()
        self.ready()
        expect(self.page.locator(CHART)).to_have_count(0)
        self.button('rimuovi_modello').click()
        self.upload()

    def test_navigation_and_responsive_actions(self):
        expect(self.button('percorso_avanti')).to_be_disabled()
        self.upload()
        self.button('percorso_avanti').click()
        purpose = self.page.get_by_label('A cosa serve, dove va montato')
        expect(purpose).to_be_visible()
        purpose.fill('Staffa sintetica per test browser')
        purpose.press('Tab')
        for width, height in ((1366, 768), (1440, 900), (390, 844)):
            with self.subTest(viewport=(width, height)):
                self.page.set_viewport_size({'width': width, 'height': height})
                self.visible_without_scroll(self.button('percorso_avanti'))
                self.visible_without_scroll(self.button('percorso_indietro'))
                self.assertTrue(self.page.evaluate(
                    '() => document.documentElement.scrollWidth <= window.innerWidth + 1'))
        self.page.set_viewport_size({'width': 1366, 'height': 768})
        self.button('percorso_avanti').click()
        expect(self.page.get_by_role('heading', name=re.compile('Che cosa conta'))).to_be_visible()
        self.visible_without_scroll(self.button('percorso_avanti'))
        self.button('percorso_avanti').click()
        expect(self.page.get_by_role('heading', name=re.compile('Tutto pronto'))).to_be_visible()
        self.visible_without_scroll(self.page.get_by_role('button', name=re.compile('Avvia analisi')))
        expect(self.page.locator('.st-key-wizard_layout')).to_contain_text('Staffa sintetica per test browser')
        self.button('percorso_indietro').click()
        expect(self.page.get_by_role('heading', name=re.compile('Che cosa conta'))).to_be_visible()
        self.button('percorso_indietro').click()
        expect(purpose).to_have_value('Staffa sintetica per test browser')
        for name in ('Diario', 'Bobine', 'Storico', 'Impostazioni', 'Analisi'):
            tab = self.page.locator('.st-key-navigazione').get_by_role('tab').filter(has_text=name)
            tab.click()
            self.ready()
            expect(tab).to_have_attribute('aria-selected', 'true')

    def test_webgl_render_and_orbit(self):
        self.upload()
        plot = self.page.locator(CHART)
        image = Image.open(io.BytesIO(plot.screenshot())).convert('RGB')
        # A real rendered mesh must produce shaded pixels, not just an empty canvas.
        colors = image.getcolors(image.width * image.height)
        self.assertGreater(len(colors), 30)
        facecolors = plot.evaluate("p => p.data.find(t => t.type === 'mesh3d').facecolor")
        shades = [ImageColor.getrgb(color) for color in set(facecolors)]
        painted = sum(count for count, rgb in colors
                      if any(max(abs(a - b) for a, b in zip(rgb, shade)) <= 3 for shade in shades))
        self.assertGreater(painted, 100, 'Mesh colours absent from the rendered image')
        self.assertEqual(plot.evaluate("p => p.data.find(t => t.type === 'mesh3d').i.length"), 12)
        before = plot.evaluate('p => p._fullLayout.scene._scene.getCamera()')
        box = plot.bounding_box()
        self.page.mouse.move(box['x'] + box['width'] * .5, box['y'] + box['height'] * .5)
        self.page.mouse.down()
        self.page.mouse.move(box['x'] + box['width'] * .7, box['y'] + box['height'] * .6, steps=12)
        self.page.mouse.up()
        self.page.wait_for_function("""({selector, before}) => JSON.stringify(
            document.querySelector(selector)._fullLayout.scene._scene.getCamera()) !== JSON.stringify(before)
        """, arg={'selector': CHART, 'before': before})
        def painted_pixels():
            screenshot = Image.open(io.BytesIO(plot.screenshot())).convert('RGB')
            return sum(count for count, rgb in screenshot.getcolors(screenshot.width * screenshot.height)
                       if any(max(abs(a - b) for a, b in zip(rgb, shade)) <= 3 for shade in shades))

        # Orthographic zoom changes the rendered scale, not necessarily getCamera().eye.
        before_zoom = painted_pixels()
        self.page.mouse.wheel(0, -300)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if abs(painted_pixels() - before_zoom) > before_zoom * .05:
                break
        else:
            self.fail('Mouse-wheel zoom did not change the rendered mesh size')


if __name__ == '__main__':
    unittest.main(verbosity=2)
