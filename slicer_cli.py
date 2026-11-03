"""Sezionamento reale con ElegooSlicer (OrcaSlicer) da riga di comando.

Lo slicer non ha un'API: si usa il suo eseguibile con le opzioni di OrcaSlicer
(--slice, --load-settings, --load-filaments, --outputdir) e si leggono i numeri
che scrive in testa e in coda al G-code (filamento, tempo, ecc.).
I profili di sistema ereditano l'uno dall'altro ("inherits"): qui vengono
appiattiti in profili completi prima di passarli allo slicer.
"""
import json
import math
import re
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

import config
from persistenza import salva_json, impronta, impronta_file
from validazione import risultato_valido

ESEGUIBILE = Path(r"C:\Program Files\ElegooSlicer\elegoo-slicer.exe")
PROFILI = Path(r"C:\Program Files\ElegooSlicer\resources\profiles\Elegoo")
VERSIONE_PROFILO_UTENTE = "1.5.3.4"


def disponibile():
    return ESEGUIBILE.exists() and PROFILI.exists()


def _indice():
    files = tuple((str(f), f.stat().st_mtime_ns, f.stat().st_size) for f in sorted(PROFILI.rglob("*.json")))
    return _carica_indice(files)


@lru_cache(maxsize=1)
def _carica_indice(files):
    indice = {}
    for percorso, _, _ in files:
        f = Path(percorso)
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(j, dict) and "name" in j:
            indice.setdefault(j["name"], j)
    return indice


def filamenti_disponibili():
    """Profili filamento di sistema per la Centauri Carbon (suffisso @ECC)."""
    return sorted(n for n, j in _indice().items()
                  if j.get("type") == "filament" and n.endswith("@ECC") and j.get("instantiation") != "false")


def profilo(nome, modifiche=None):
    """Profilo completo: la catena di 'inherits' fusa dal più generico al più specifico."""
    catena, n = [], nome
    indice = _indice()
    while n:
        j = indice.get(n)
        if j is None:
            raise KeyError(f"profilo non trovato: {n}")
        catena.append(j)
        n = j.get("inherits")
    completo = {}
    for j in reversed(catena):
        completo.update(j)
    completo.pop("inherits", None)
    completo["name"] = nome
    # resta "system": per i profili utente la riga di comando ricava il nome della stampante da
    # "inherits" (tolto qui) e il controllo di compatibilità processo/stampante fallirebbe (-17)
    completo["from"] = "system"
    completo.update(modifiche or {})
    return completo


def profilo_utente(nome, processo_base, impostazioni, supporti=None):
    """Profilo di processo completo e importabile con le impostazioni realmente provate."""
    nome = str(nome).strip()
    if not nome:
        raise ValueError("il nome del profilo non può essere vuoto")
    modifiche = dict(supporti or {})
    modifiche.update(impostazioni)
    esportato = profilo(processo_base, modifiche)
    esportato.pop("setting_id", None)
    esportato.pop("instantiation", None)
    esportato.update({
        "from": "User", "is_custom_defined": "0", "name": nome,
        "print_settings_id": nome, "version": VERSIONE_PROFILO_UTENTE,
    })
    return esportato


NUMERI_GCODE = {
    "filamento_mm": r";\s*filament used \[mm\]\s*=\s*([\d.]+)",
    "filamento_cm3": r";\s*filament used \[cm3\]\s*=\s*([\d.]+)",
    "filamento_g": r";\s*(?:total )?filament used \[g\]\s*=\s*([\d.]+)",
    "costo": r";\s*(?:total )?filament cost\s*=\s*([\d.]+)",
    "tempo": r";\s*(?:model printing time|estimated printing time \(normal mode\))\s*[:=]\s*([^;\n]+)",
    "strati": r";\s*total layer number:\s*(\d+)",
}


def leggi_gcode(percorso):
    testo = Path(percorso).read_text(encoding="utf-8", errors="replace")
    testa, coda = testo[:20000], testo[-40000:]
    out = {}
    for chiave, rx in NUMERI_GCODE.items():
        m = re.search(rx, testa + coda)
        if m:
            v = m.group(1).strip()
            out[chiave] = float(v) if re.fullmatch(r"[\d.]+", v) else v
    return out


TIPI_SUPPORTO = {"Support", "Support interface", "Support transition"}


def filamento_per_tipo(percorso, diametro=1.75, densita=1.25):
    """Grammi di filamento per tipo di estrusione (;TYPE:...), con estrusione relativa (M83).
    Si contano solo i movimenti con X o Y: i recuperi dopo una retrazione non sono materiale depositato."""
    sezione = math.pi * (diametro / 2) ** 2
    mm, tipo = {}, "Altro"
    for riga in Path(percorso).read_text(encoding="utf-8", errors="replace").splitlines():
        if riga.startswith(";TYPE:"):
            tipo = riga[6:].strip()
        elif riga.startswith(("G1 ", "G2 ", "G3 ")) and (" X" in riga or " Y" in riga):
            m = re.search(r" E(-?[\d.]+)", riga.split(";")[0])
            if m and float(m.group(1)) > 0:
                mm[tipo] = mm.get(tipo, 0.0) + float(m.group(1))
    return {t: round(v * sezione * densita / 1000, 3) for t, v in mm.items()}


def secondi(tempo):
    """'1h 2m 3s' -> 3723."""
    unita = {"d": 86400, "h": 3600, "m": 60, "s": 1}
    return sum(int(n) * unita[u] for n, u in re.findall(r"(\d+)\s*([dhms])", str(tempo)))


def risultato_gcode(percorso, filamento):
    """Estrae dal G-code tutti i numeri usati dalla dashboard."""
    numeri = leggi_gcode(percorso)
    diametro = float(str(filamento.get("filament_diameter", ["1.75"])[0]))
    densita = float(str(filamento.get("filament_density", ["1.25"])[0]))
    per_tipo = filamento_per_tipo(percorso, diametro, densita)
    supporti = sum(v for t, v in per_tipo.items() if t in TIPI_SUPPORTO)
    brim, avvio = per_tipo.get("Brim", 0.0), per_tipo.get("Custom", 0.0)
    # "filamento_g" è il totale dichiarato dallo slicer; le voci sotto sono misurate sui movimenti
    # del G-code e sommano il filamento davvero estruso (il dichiarato conta anche ~retrazioni/spurgo)
    risultato = {"gcode": str(percorso), **numeri,
            "tempo_s": secondi(numeri.get("tempo", "")),
            "pezzo_g": round(sum(per_tipo.values()) - supporti - brim - avvio, 2),
            "supporti_g": round(supporti, 2), "brim_g": round(brim, 2), "linea_avvio_g": round(avvio, 2),
            "estruso_g": round(sum(per_tipo.values()), 2),
            "per_tipo_g": per_tipo}
    with Path(percorso).open("rb") as f:
        f.seek(max(0, Path(percorso).stat().st_size - 40000))
        completo = b"; CONFIG_BLOCK_END" in f.read()
    if not completo or not risultato_valido(risultato) or not numeri.get("strati"):
        raise ValueError("G-code incompleto o privo di tempo, materiale o strati validi")
    risultato["consumo_totale_g"] = max(risultato["estruso_g"], risultato.get("filamento_g", 0))
    return risultato


def contesto(stl, macchina, processo, filamento):
    stat = ESEGUIBILE.stat()
    motore = ESEGUIBILE.parent / "ElegooSlicer.dll"
    motore_stat = motore.stat() if motore.exists() else None
    versione = _firma_eseguibile(str(ESEGUIBILE), str(motore), stat.st_size, stat.st_mtime_ns,
                                 motore_stat.st_size if motore_stat else 0,
                                 motore_stat.st_mtime_ns if motore_stat else 0)
    return impronta({"stl": impronta_file(stl), "macchina": macchina, "processo": processo,
                     "filamento": filamento, "slicer": versione,
                     "parser": 2})


@lru_cache(maxsize=4)
def _firma_eseguibile(percorso, motore_percorso, dimensione, modificato, dimensione_motore, modificato_motore):
    motore = Path(motore_percorso)
    return [percorso, impronta_file(percorso), impronta_file(motore) if motore.exists() else None]


def cache_valida(cartella, chiave, nome="cache.json", artefatto=None):
    cartella = Path(cartella)
    try:
        dati = json.loads((cartella / nome).read_text(encoding="utf-8"))
        file = Path(artefatto) if artefatto else cartella / dati["file"]
        return dati["contesto"] == chiave and dati["sha256"] == impronta_file(file)
    except (OSError, ValueError, KeyError, TypeError):
        return False


def salva_cache(cartella, chiave, artefatto, nome="cache.json"):
    salva_json(Path(cartella) / nome, {"contesto": chiave, "file": Path(artefatto).name,
                                     "sha256": impronta_file(artefatto)})


def seziona(stl, macchina, processo, filamento, cartella=None, timeout=600):
    """Seziona un STL (già orientato) e ritorna i numeri del G-code. I profili sono dict completi."""
    cartella = Path(cartella or tempfile.mkdtemp(prefix="seziona_"))
    cartella.mkdir(parents=True, exist_ok=True)
    stl = Path(stl).resolve()
    cartella = cartella.resolve()
    chiave = contesto(stl, macchina, processo, filamento)
    if cache_valida(cartella, chiave):
        metadati = json.loads((cartella / "cache.json").read_text(encoding="utf-8"))
        return risultato_gcode(cartella / metadati["file"], filamento)
    percorsi = {}
    for nome, prof in (("macchina", macchina), ("processo", processo), ("filamento", filamento)):
        percorsi[nome] = cartella / f"{nome}.json"
        percorsi[nome].write_text(json.dumps(prof, ensure_ascii=False), encoding="utf-8")
    # Se il profilo è cambiato, un G-code precedente non deve mascherare un nuovo fallimento.
    for vecchio in cartella.glob("*.gcode"):
        vecchio.unlink()
    comando = [str(ESEGUIBILE), "--slice", "0", "--arrange", "1",
               "--load-settings", f"{percorsi['macchina']};{percorsi['processo']}",
               "--load-filaments", str(percorsi["filamento"]),
               "--outputdir", str(cartella), str(stl)]
    r = subprocess.run(comando, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout, cwd=str(cartella))
    (cartella / "log.txt").write_text((r.stdout or "") + "\n" + (r.stderr or ""), encoding="utf-8")
    gcode = sorted(cartella.glob("*.gcode"))
    if r.returncode != 0 or not gcode:
        raise RuntimeError(f"nessun G-code prodotto (uscita {r.returncode}), vedi {cartella / 'log.txt'}")
    risultato = risultato_gcode(gcode[0], filamento)
    salva_cache(cartella, chiave, gcode[0])
    return risultato


def profili(processo, filamento, modifiche_processo=None):
    """Stampante dalla configurazione + processo e filamento scelti, appiattiti."""
    return (profilo(config.PROFILO_STAMPANTE), profilo(processo, modifiche_processo), profilo(filamento))


def progetto_valido(stl, destinazione, processo, filamento, modifiche):
    macchina, proc, fil = profili(processo, filamento, modifiche)
    destinazione = Path(destinazione)
    return cache_valida(destinazione.parent, contesto(stl, macchina, proc, fil),
                        destinazione.name + ".json", destinazione)


def esporta_3mf(stl, destinazione, processo, filamento, modifiche_processo=None, timeout=600):
    """Crea con ElegooSlicer un progetto 3MF con modello orientato e profili completi."""
    stl, destinazione = Path(stl).resolve(), Path(destinazione).resolve()
    destinazione.parent.mkdir(parents=True, exist_ok=True)
    if destinazione.exists():
        destinazione.unlink()
    macchina, proc, fil = profili(processo, filamento, modifiche_processo)
    chiave = contesto(stl, macchina, proc, fil)
    with tempfile.TemporaryDirectory(prefix="profilo_3mf_") as temporanea:
        temporanea = Path(temporanea)
        percorsi = {}
        for nome, prof in (("macchina", macchina), ("processo", proc), ("filamento", fil)):
            percorsi[nome] = temporanea / f"{nome}.json"
            percorsi[nome].write_text(json.dumps(prof, ensure_ascii=False), encoding="utf-8")
        comando = [str(ESEGUIBILE), "--slice", "0",
                   "--load-settings", f"{percorsi['macchina']};{percorsi['processo']}",
                   "--load-filaments", str(percorsi["filamento"]),
                   "--outputdir", str(destinazione.parent),
                   "--export-3mf", destinazione.name, str(stl)]
        esito = subprocess.run(comando, capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=timeout, cwd=str(destinazione.parent))
    if not destinazione.is_file() or destinazione.stat().st_size == 0:
        dettaglio = ((esito.stdout or "") + "\n" + (esito.stderr or "")).strip()[-500:]
        raise RuntimeError(f"progetto 3MF non prodotto (uscita {esito.returncode}): {dettaglio}")
    import zipfile
    with zipfile.ZipFile(destinazione) as archivio:
        if archivio.testzip() or "Metadata/project_settings.config" not in archivio.namelist():
            raise ValueError("Archivio 3MF non valido")
    salva_cache(destinazione.parent, chiave, destinazione, destinazione.name + ".json")
    return destinazione


def seziona_orientamenti(mesh, orientamenti, cartella, processo, filamento, modifiche_processo=None,
                         avanzamento=None):
    """Seziona ogni orientamento candidato (STL già ruotato e appoggiato sul piatto).
    Ritorna {id: risultati} e scrive i risultati anche dentro ogni orientamento.
    avanzamento(i, o), se c'è, viene chiamata prima di sezionare l'i-esimo orientamento."""
    macchina, proc, fil = profili(processo, filamento, modifiche_processo)
    cartella = Path(cartella)
    risultati = {}
    for i, o in enumerate(orientamenti):
        if avanzamento:
            avanzamento(i, o)
        sotto = cartella / f"orientamento_{o['id']}"
        sotto.mkdir(parents=True, exist_ok=True)
        m = mesh.copy()
        m.apply_transform(o["trasformazione"])
        m.apply_translation(-m.bounds[0])
        stl = sotto / "pezzo.stl"
        m.export(stl)
        try:
            r = seziona(stl, macchina, proc, fil, sotto)
            r.pop("gcode", None)
        except Exception as e:
            r = {"errore": str(e)[:300]}
        risultati[o["id"]] = r
        o["slicer"] = r
    return risultati


def seziona_varianti(mesh, orientamenti, cartella, processo, filamento, varianti, avanzamento=None, supporti=None):
    """Seziona le varianti non di riferimento per gli orientamenti ricevuti.

    La variante di riferimento è già presente in ``orientamento['slicer']`` e viene saltata.
    Ritorna record JSON-serializzabili con orientamento, variante e risultato.
    """
    macchina = profilo(config.PROFILO_STAMPANTE)
    fil = profilo(filamento)
    processo_base = profilo(processo)
    cartella = Path(cartella)
    da_eseguire = [(o, v) for o in orientamenti for v in varianti if not v.get("riferimento")]
    risultati = []
    for indice, (o, variante) in enumerate(da_eseguire):
        if avanzamento:
            avanzamento(indice, o, variante, len(da_eseguire))
        sotto = cartella / f"orientamento_{o['id']}" / variante["id"]
        sotto.mkdir(parents=True, exist_ok=True)
        m = mesh.copy()
        m.apply_transform(o["trasformazione"])
        m.apply_translation(-m.bounds[0])
        stl = sotto / "pezzo.stl"
        m.export(stl)
        proc = dict(processo_base)
        proc.update(config.SUPPORTI_SEZIONAMENTO if supporti is None else supporti)
        proc.update(variante["impostazioni"])
        try:
            r = seziona(stl, macchina, proc, fil, sotto)
            r.pop("gcode", None)
        except Exception as e:
            r = {"errore": str(e)[:300]}
        risultati.append({"orientamento_id": o["id"], "variante_id": variante["id"], "risultato": r})
    return risultati
