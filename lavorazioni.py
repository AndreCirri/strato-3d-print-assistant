"""Processi separati da Streamlit, con stato e risultati salvati atomicamente."""
import json
import os
import subprocess
import sys
import traceback
import time
from pathlib import Path

from persistenza import salva_json


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
                                               "modo": modo, "fase": "Avvio"})
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
    def progresso(fase):
        salva_json(cartella / "lavorazione.json", {"stato": "in corso", "pid": os.getpid(),
                                                   "modo": modo, "fase": fase})
    try:
        progresso("Avvio")
        richiesta = json.loads((cartella / "richiesta.json").read_text(encoding="utf-8"))
        if modo == "3mf":
            spec = json.loads((cartella / "esportazione.json").read_text(encoding="utf-8"))
            progresso("Esportazione 3MF")
            slicer_cli.esporta_3mf(cartella / spec["stl"], cartella / spec["destinazione"],
                                  spec["processo"], spec["filamento"], spec["modifiche"])
            salva_json(cartella / "lavorazione.json", {"stato": "completata", "modo": modo, 'pid': os.getpid()})
            return
        if (cartella / "analisi.json").exists():
            dati = json.loads((cartella / "analisi.json").read_text(encoding="utf-8"))
            modello = cartella / Path(dati["file"]).name
            mesh = analisi.carica(modello)
            if dati.get("versione_geometria", 1) < config.VERSIONE_GEOMETRIA:
                progresso("Aggiornamento geometria")
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
                augura_addon.step_in_stl(originale, modello)
            progresso("Analisi geometrica")
            mesh, dati = analisi.analizza(modello)
            dati["sha256"] = ingresso["sha256"]
            salva_json(cartella / "analisi.json", dati)
        if modo == "completa":
            if slicer_cli.disponibile():
                sez = dati.setdefault("sezionamento", {
                    "processo": config.PROFILO_PROCESSO,
                    "filamento": richiesta.get("profilo_filamento", config.PROFILO_FILAMENTO),
                    "supporti": config.SUPPORTI_SEZIONAMENTO})
                progresso("Sezionamento degli orientamenti")
                slicer_cli.seziona_orientamenti(mesh, dati["orientamenti"], cartella / "sezionamenti",
                                                sez["processo"], sez["filamento"], sez["supporti"])
                classifica.applica(dati)
                salva_json(cartella / "analisi.json", dati)
        if modo in ("completa", "varianti") and slicer_cli.disponibile():
            progresso("Confronto dei processi")
            confronto.calcola(mesh, dati, cartella, richiesta,
                              lambda i, o, v, n: progresso(f"{v['nome']}, orientamento {o['id']} ({i+1}/{n})"))
            salva_json(cartella / "analisi.json", dati)
        if modo in ('completa', 'varianti', 'controlli'):
            progresso('Controlli di cavità, sezioni e toolpath')
            diagnostica.calcola(cartella, dati, mesh)
            salva_json(cartella / 'analisi.json', dati)
        if modo in ("completa", "immagini"):
            progresso("Creazione immagini")
            render.griglia_orientamenti(mesh, dati["orientamenti"], cartella / "orientamenti.png")
            for o in dati["orientamenti"][:2]:
                render.viste(mesh, o["trasformazione"], cartella / f"viste_{o['id']}.png")
            dati["immagini_da_aggiornare"] = False
            salva_json(cartella / "analisi.json", dati)
        if modo == "completa":
            ingresso_path = cartella / "ingresso.json"
            ingresso = json.loads(ingresso_path.read_text(encoding="utf-8")) if ingresso_path.exists() else {}
            if Path(ingresso.get("file", "")).suffix.lower() in (".step", ".stp"):
                import augura_addon
                if augura_addon.disponibile():
                    progresso("Controlli STEP")
                    dati["augura"] = augura_addon.verifica(cartella / ingresso["file"])
                    salva_json(cartella / "analisi.json", dati)
        salva_json(cartella / "lavorazione.json", {"stato": "completata", "modo": modo, 'pid': os.getpid()})
    except Exception as errore:
        traceback.print_exc()
        salva_json(cartella / "lavorazione.json", {"stato": "errore", "modo": modo, 'pid': os.getpid(), "errore": str(errore)})
    finally:
        (cartella / "lavorazione.lock").unlink(missing_ok=True)


if __name__ == "__main__":
    esegui(sys.argv[1], sys.argv[2])
