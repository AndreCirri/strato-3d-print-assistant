"""Processi separati da Streamlit, con stato e risultati salvati atomicamente."""
import json
import os
import subprocess
import sys
import traceback
import time
from pathlib import Path

from persistenza import salva_json
from avanzamento import Avanzamento


def stato(cartella):
    try:
        dati = json.loads((Path(cartella) / "lavorazione.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if dati.get("stato") == "in corso" and not vivo(dati.get("pid")):
        # Il worker può aver scritto l'esito finale tra la lettura e il controllo del PID.
        try:
            dati = json.loads((Path(cartella) / "lavorazione.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        if dati.get("stato") == "in corso":
            dati["stato"] = "interrotta"
    return dati


def vivo(pid):
    if not pid:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, int(pid))
        if not handle:
            return False
        code = wintypes.DWORD()
        try:
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def avvia(cartella, modo="completa"):
    cartella = Path(cartella).resolve()
    lock = cartella / "lavorazione.lock"
    if stato(cartella).get("stato") == "in corso":
        return
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            pid = int(lock.read_text())
        except (ValueError, OSError):
            if lock.exists() and time.time() - lock.stat().st_mtime > 5:
                lock.unlink(missing_ok=True)
                return avvia(cartella, modo)
            return  # un altro avvio sta ancora scrivendo il lock
        if vivo(pid):
            return
        lock.unlink()
        return avvia(cartella, modo)
    with os.fdopen(fd, "w") as f:
        f.write(str(os.getpid()))
    salva_json(cartella / "lavorazione.json", {"stato": "in corso", "pid": os.getpid(),
                                               "modo": modo, "fase": "Avvio", 'frazione': 0., 'inizio': time.time()})
    try:
        with (cartella / "lavorazione.log").open("a", encoding="utf-8") as log:
            processo = subprocess.Popen([sys.executable, '-X', 'faulthandler', str(Path(__file__).resolve()), str(cartella), modo],
                                        cwd=Path(__file__).parent, stdout=log, stderr=log,
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        lock.write_text(str(processo.pid))
    except Exception:
        lock.unlink(missing_ok=True)
        salva_json(cartella / "lavorazione.json", {"stato": "errore", "modo": modo, "errore": "Avvio fallito"})
        raise


def esegui(cartella, modo):
    import config
    import analisi
    import classifica
    import confronto
    import render
    import slicer_cli
    import diagnostica
    cartella = Path(cartella)
    avanzamento = Avanzamento(cartella, modo)
    progresso = avanzamento.aggiorna
    try:
        progresso("Avvio", 0.)
        richiesta = json.loads((cartella / "richiesta.json").read_text(encoding="utf-8"))
        if modo == "3mf":
            spec = json.loads((cartella / "esportazione.json").read_text(encoding="utf-8"))
            progresso("Esportazione 3MF", .05, 0, 1)
            slicer_cli.esporta_3mf(cartella / spec["stl"], cartella / spec["destinazione"],
                                  spec["processo"], spec["filamento"], spec["modifiche"])
            avanzamento.termina()
            return
        if (cartella / "analisi.json").exists():
            dati = json.loads((cartella / "analisi.json").read_text(encoding="utf-8"))
            modello = cartella / Path(dati["file"]).name
            progresso('Caricamento del modello', .02)
            mesh = analisi.carica(modello)
            if dati.get("versione_geometria", 1) < config.VERSIONE_GEOMETRIA:
                progresso("Aggiornamento geometria", .04)
                analisi.aggiorna_geometria(mesh, dati)
                classifica.applica(dati)
                dati.pop("ottimizzazione_processo", None)
                dati["immagini_da_aggiornare"] = True
                salva_json(cartella / "analisi.json", dati)
        else:
            ingresso = json.loads((cartella / "ingresso.json").read_text(encoding="utf-8"))
            modello = cartella / ingresso["file"]
            if modello.suffix.lower() in (".step", ".stp"):
                import augura_addon
                originale = modello
                modello = modello.with_suffix(".stl")
                progresso('Conversione STEP', .02)
                augura_addon.step_in_stl(originale, modello)
            progresso("Analisi geometrica", .04)
            mesh, dati = analisi.analizza(modello)
            dati["sha256"] = ingresso["sha256"]
            salva_json(cartella / "analisi.json", dati)
        if modo == "completa":
            if slicer_cli.disponibile():
                sez = dati.setdefault("sezionamento", {
                    "processo": config.PROFILO_PROCESSO,
                    "filamento": richiesta.get("profilo_filamento", config.PROFILO_FILAMENTO),
                    "supporti": config.SUPPORTI_SEZIONAMENTO})
                salva_json(cartella / "analisi.json", dati)
        if modo in ("completa", "varianti") and slicer_cli.disponibile():
            progresso("Confronto dei processi", .1)
            confronto.calcola(mesh, dati, cartella, richiesta,
                              progresso=lambda frazione, fase, completati, totale:
                                progresso(fase, .1 + .7 * frazione, completati, totale))
            salva_json(cartella / "analisi.json", dati)
        if modo in ('completa', 'varianti', 'controlli'):
            base_controlli = .8 if modo in ('completa', 'varianti') else .1
            ampiezza = .1 if modo == 'completa' else .89 if modo == 'controlli' else .19
            progresso('Controlli di cavità, sezioni e toolpath', base_controlli)
            diagnostica.calcola(cartella, dati, mesh,
                avanzamento=lambda f, fase: progresso(fase, base_controlli + ampiezza * f))
            salva_json(cartella / 'analisi.json', dati)
        if modo in ("completa", "immagini"):
            base_immagini = .9 if modo == 'completa' else .1
            totale_immagini = 1 + min(2, len(dati['orientamenti']))
            progresso("Creazione griglia orientamenti", base_immagini, 0, totale_immagini)
            render.griglia_orientamenti(mesh, dati["orientamenti"], cartella / "orientamenti.png")
            for i, o in enumerate(dati["orientamenti"][:2], 1):
                progresso(f"Creazione viste — orientamento {o['id']}",
                          base_immagini + (.98 - base_immagini) * i / totale_immagini, i, totale_immagini)
                render.viste(mesh, o["trasformazione"], cartella / f"viste_{o['id']}.png")
            dati["immagini_da_aggiornare"] = False
            salva_json(cartella / "analisi.json", dati)
        if modo == "completa":
            ingresso_path = cartella / "ingresso.json"
            ingresso = json.loads(ingresso_path.read_text(encoding="utf-8")) if ingresso_path.exists() else {}
            if Path(ingresso.get("file", "")).suffix.lower() in (".step", ".stp"):
                import augura_addon
                if augura_addon.disponibile():
                    progresso("Controlli STEP", .98, 0, 1)
                    dati["augura"] = augura_addon.verifica(cartella / ingresso["file"])
                    salva_json(cartella / "analisi.json", dati)
        avanzamento.termina()
    except Exception as errore:
        traceback.print_exc()
        avanzamento.termina(errore)
    finally:
        (cartella / "lavorazione.lock").unlink(missing_ok=True)


if __name__ == "__main__":
    esegui(sys.argv[1], sys.argv[2])
