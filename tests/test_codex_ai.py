"""Contratto del processo Codex: allegati, errori e instradamento senza chiamate online."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import codex_ai
import consiglio


class CodexTest(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "Il collegamento simbolico richiede privilegi su Windows")
    def test_cli_locale_con_collegamento_interrotto(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            collegamento = home / ".local/bin/codex"
            collegamento.parent.mkdir(parents=True)
            collegamento.symlink_to(home / ".codex/packages/standalone/current/bin/codex")
            cli = home / ".codex/packages/app-server-daemon/current/bin/codex"
            cli.parent.mkdir(parents=True)
            cli.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            cli.chmod(0o755)
            with patch.dict(os.environ, {}, clear=True), \
                 patch("codex_ai.Path.home", return_value=home), \
                 patch("codex_ai.shutil.which", return_value=None):
                self.assertEqual(codex_ai.eseguibile(), str(cli))

    def test_percorsi_cli_e_codex_home(self):
        nome = "codex.exe" if os.name == "nt" else "codex"
        for percorso in (f".local/bin/{nome}",
                         f".codex/packages/standalone/current/bin/{nome}",
                         f".codex/packages/app-server-daemon/current/bin/{nome}",
                         f"profilo/packages/app-server-daemon/current/bin/{nome}"):
            with self.subTest(percorso=percorso), tempfile.TemporaryDirectory() as tmp:
                home = Path(tmp)
                cli = home / percorso
                cli.parent.mkdir(parents=True)
                cli.write_bytes(b"cli")
                cli.chmod(0o755)
                ambiente = {"CODEX_HOME": str(home / "profilo")} if percorso.startswith("profilo/") else {}
                with patch.dict(os.environ, ambiente, clear=True), \
                     patch("codex_ai.Path.home", return_value=home), \
                     patch("codex_ai.shutil.which", return_value=None):
                    self.assertEqual(codex_ai.eseguibile(), str(cli))

    def test_priorita_override_e_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            cli = Path(tmp) / "codex"
            cli.write_bytes(b"cli")
            with patch.dict(os.environ, {"STRATO_CODEX_EXE": str(cli)}), \
                 patch("codex_ai.shutil.which") as which:
                self.assertEqual(codex_ai.eseguibile(), str(cli))
                which.assert_not_called()
            with patch.dict(os.environ, {}, clear=True), \
                 patch("codex_ai.shutil.which", return_value=str(cli)):
                self.assertEqual(codex_ai.eseguibile(), str(cli))


    def test_risposta_immagini_e_permessi(self):
        with tempfile.TemporaryDirectory() as tmp:
            foto = Path(tmp) / "pezzo con spazi.png"
            foto.write_bytes(b"immagine")

            def esegui(args, **kwargs):
                self.assertEqual(args[:2], ["codex.exe", "exec"])
                self.assertEqual(args[args.index("--sandbox") + 1], "read-only")
                self.assertIn("--ignore-user-config", args)
                self.assertIn("--ephemeral", args)
                self.assertEqual(args[args.index("--image") + 1], str(foto.resolve()))
                self.assertNotIn("--model", args)
                self.assertEqual(args[-1], "-")
                self.assertIn("Analisi del pezzo", kwargs["input"])
                self.assertNotIn("shell", kwargs)
                Path(args[args.index("--output-last-message") + 1]).write_text(
                    "## Orientamento\nScelta: 2\nPerché è stabile.", encoding="utf-8")
                return subprocess.CompletedProcess(args, 0, "log", "")

            with patch("codex_ai.eseguibile", return_value="codex.exe"), \
                 patch("codex_ai.subprocess.run", side_effect=esegui):
                testo, costo, errore = consiglio.chiedi("Analisi del pezzo", tmp, "", "Codex", [foto])
            self.assertEqual(consiglio.orientamento_scelto(testo), 2)
            self.assertIsNone(costo)
            self.assertIsNone(errore)

    def test_mancanza_cli(self):
        with patch("codex_ai.eseguibile", return_value=None):
            self.assertIn("non trovato", codex_ai.chiedi_codex("p", ".", "s")[2])

    def test_errori_processo_e_risposta_vuota(self):
        for risultato, atteso in [
            (subprocess.CompletedProcess([], 1, "", "login richiesto"), "login"),
            (subprocess.CompletedProcess([], 0, "", ""), "vuota"),
        ]:
            with self.subTest(atteso=atteso), \
                 patch("codex_ai.eseguibile", return_value="codex.exe"), \
                 patch("codex_ai.subprocess.run", return_value=risultato):
                self.assertIn(atteso, codex_ai.chiedi_codex("p", ".", "s")[2])

    def test_timeout(self):
        with patch("codex_ai.eseguibile", return_value="codex.exe"), \
             patch("codex_ai.subprocess.run", side_effect=subprocess.TimeoutExpired("codex", 300)):
            self.assertIn("5 minuti", codex_ai.chiedi_codex("p", ".", "s")[2])

    def test_immagini_mancanti_non_inviano_richieste(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch("codex_ai.eseguibile", return_value="codex.exe"), \
             patch("codex_ai.subprocess.run") as run:
            errore = codex_ai.chiedi_codex("p", tmp, "s", immagini=[Path(tmp) / "mancante.png"])[2]
            self.assertIn("immagini", errore)
            run.assert_not_called()

    def test_modello_personalizzato(self):
        with patch("codex_ai.eseguibile", return_value="codex.exe"), \
             patch("codex_ai.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "", "")) as run:
            codex_ai.chiedi_codex("p", ".", "s", "modello-scelto")
            args = run.call_args.args[0]
            self.assertEqual(args[args.index("--model") + 1], "modello-scelto")

    def test_claude_resta_predefinito(self):
        async def risposta(*args):
            return "Claude", 0.1, None
        with patch("consiglio._chiedi", side_effect=risposta) as chiedi:
            self.assertEqual(consiglio.chiedi("p", "."), ("Claude", 0.1, None))
            chiedi.assert_called_once()


if __name__ == "__main__":
    unittest.main()
