"""Le chiamate a Claude tramite il Claude Agent SDK (usa il login di Claude Code di questo PC).

Claude riceve solo dati già calcolati e le immagini da guardare con lo strumento Read:
non può modificare file né eseguire comandi.
"""
import asyncio
import json
import re
from pathlib import Path

import config

SISTEMA = """Sei un tutor esperto di stampa 3D FDM. Aiuti una persona che sa programmare ma sta \
imparando la stampa: oltre a dire cosa impostare, spieghi sempre il perché, in modo che la volta \
dopo sappia decidere da sola.

Regole:
- I numeri dell'analisi geometrica sono misurati dal codice: usali e citali, non inventarne altri. \
Se un dato manca o è incerto, dillo.
- Guarda le immagini con lo strumento Read prima di decidere: rosso = superficie che chiede supporti \
che partono dal piatto, arancione = supporti che poggerebbero sul pezzo (i più difficili da togliere).
- Se l'analisi contiene "augura", sono controlli di un secondo strumento: esatti per i file STEP \
(ponti, spessori, orientamenti), approssimati per gli STL. Se i due strumenti non concordano, dillo e \
spiega quale è più affidabile in quel caso.
- "scelto_da_slicer" e "confronto_slicer" riproducono l'orientamento automatico di OrcaSlicer/ElegooSlicer \
con lo stesso algoritmo: la sua formula premia poche sporgenze e la base dell'involucro convesso, quindi a \
volte sceglie pose inclinate che toccano il piatto solo con spigoli.
- Se un orientamento ha il campo "slicer", sono i numeri di un sezionamento reale con ElegooSlicer \
(grammi di pezzo, supporti e brim misurati nel G-code, tempo stimato dallo slicer, profilo in "sezionamento"): \
valgono più delle stime geometriche, che non vedono per esempio i supporti che lo slicer aggiunge sotto \
spigoli e punte. Quando stime e sezionamento non concordano, segui il sezionamento e dillo.
- Se "classifica.metodo" è "sezionamento_reale", l'ordine degli orientamenti e "punteggio_reale" usano \
i grammi del G-code. "supporti_sul_pezzo_stimati_g" copre invece le sporgenze che il profilo solo dal \
piatto non serve; "punteggio_geometrico" resta come confronto. Preferisci la classifica reale, ma spiega \
se il vincitore è diverso da quello geometrico.
- Se è presente "analisi_meccanica", usala per discutere la direzione degli strati. È un confronto \
euristico: non presentare l'indice come tensione, fattore di sicurezza o carico di rottura.
- Se è presente "ottimizzazione_processo", confronta i risultati reali di Dettaglio, Bilanciato e Veloce. \
La "raccomandazione" segue la priorità dichiarata dall'utente: usala come punto di partenza, cita tempo e \
materiale misurati e segnalalo chiaramente se per ragioni tecniche proponi una combinazione diversa.
- Ribaltamento e brim sono calcolati per ogni orientamento: se consigli un orientamento con brim \
consigliato, specifica tipo e larghezza del brim.
- Nomina le opzioni come nell'interfaccia italiana di ElegooSlicer/OrcaSlicer; se non sei sicuro della \
traduzione, aggiungi il nome inglese di OrcaSlicer tra parentesi.
- Dai valori concreti per la stampante e i materiali indicati, non intervalli generici.
- Se il diario contiene esperienze passate rilevanti, tienine conto e dillo.
- Scrivi in italiano semplice, senza gergo non spiegato. Usa Markdown."""

FORMATO_CONSIGLIO = """Rispondi con queste sezioni:
## In breve
Tre o quattro righe: orientamento, materiale e le due o tre impostazioni che contano di più.
## Il pezzo
Cosa noti della geometria (spessori, sporgenze, parti delicate) rispetto all'uso descritto.
## Orientamento
La prima riga della sezione deve essere esattamente `Scelta: N`, con N il numero del candidato scelto.
Poi perché, confrontando i numeri; cosa si sacrifica. Confrontati con "confronto_slicer": dì se per \
questo pezzo conviene fidarsi del pulsante Orienta automaticamente dello slicer, e perché.
## Materiale
## Impostazioni
Una tabella: Sezione | Opzione | Valore | Perché. Solo le opzioni da cambiare rispetto al profilo abituale.
## Supporti
Tipo, blocchi supporti da aggiungere e dove, cosa controllare nell'anteprima del sezionamento.
## Rischi
Cosa può andare storto e come accorgersene durante la stampa.
## Da imparare
Un concetto spiegato bene (5-10 righe), scelto tra quelli usati in questa risposta.
## Prova suggerita
Un piccolo esperimento per capire meglio un parametro su questo pezzo."""


def _diario_recente(n=15):
    if not config.DIARIO.exists():
        return []
    righe = config.DIARIO.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(r) for r in righe[-n:] if r.strip()]


async def _chiedi(prompt, cartella, modello):
    # l'SDK pesa qualche secondo: lo carica la prima domanda, non l'avvio della dashboard
    from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
    opzioni = ClaudeAgentOptions(
        system_prompt=SISTEMA,
        tools=["Read"],                 # può solo leggere (immagini e file della cartella)
        allowed_tools=["Read"],
        cwd=str(cartella),
        model=modello,
        max_turns=8,
        setting_sources=[],             # non carica impostazioni e memoria personali di Claude Code
    )
    testo, costo, errore = None, None, None
    async for msg in query(prompt=prompt, options=opzioni):
        if isinstance(msg, ResultMessage):
            testo, costo = msg.result, msg.total_cost_usd
            if msg.is_error:
                errore = f"{msg.subtype} (stop: {msg.stop_reason})"
    return testo, costo, errore


def orientamento_scelto(testo):
    """Il numero dopo 'Scelta:' nella sezione Orientamento del consiglio (None se manca)."""
    m = re.search(r"Scelta:\s*\**\s*(\d+)", testo or "")
    return int(m.group(1)) if m else None


def chiedi(prompt, cartella, modello="opus"):
    return asyncio.run(_chiedi(prompt, Path(cartella), modello))


def prompt_consiglio(analisi, richiesta, immagini):
    dati = json.loads(json.dumps(analisi))
    for o in dati["orientamenti"]:
        o.pop("trasformazione", None)
    return f"""Devo stampare questo pezzo. Proponi come farlo.

# Stampante
{json.dumps(config.STAMPANTE, ensure_ascii=False, indent=2)}

# Cosa mi serve
{json.dumps(richiesta, ensure_ascii=False, indent=2)}

# Analisi geometrica (misure in mm)
{json.dumps(dati, ensure_ascii=False, indent=2)}

# Immagini da guardare con Read
{chr(10).join(f"- {p}" for p in immagini)}

# Il mio diario di stampa (ultime voci)
{json.dumps(_diario_recente(), ensure_ascii=False, indent=2) or "vuoto"}

{FORMATO_CONSIGLIO}"""


def prompt_diagnosi(voce, foto):
    return f"""Ho stampato un pezzo e voglio capire com'è andata e cosa cambiare la prossima volta.

# Stampante
{json.dumps(config.STAMPANTE, ensure_ascii=False, indent=2)}

# La stampa
{json.dumps(voce, ensure_ascii=False, indent=2)}

# Foto da guardare con Read
{chr(10).join(f"- {p}" for p in foto) or "nessuna"}

# Altre voci del diario
{json.dumps(_diario_recente(), ensure_ascii=False, indent=2)}

Rispondi con: ## Cosa vedo, ## Cause probabili (in ordine di probabilità, con come verificarle), \
## Cosa cambiare (tabella Opzione | Da | A | Perché), ## Da imparare (un concetto, 5-10 righe)."""
