# Assistente di stampa 3D

Analizza un file da stampare, chiede a Claude come stamparlo e spiega il perché di ogni scelta.
Tiene un diario delle stampe, così i consigli migliorano con l'esperienza sulla tua stampante.

## Avvio

Doppio clic su `avvia.bat`: la prima volta crea l'ambiente `.venv` e installa `requirements.txt`. Oppure a mano:

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m streamlit run app.py
```

La pagina si apre su http://localhost:8501 ed è raggiungibile solo da questo PC.

## Come funziona

1. **Analisi geometrica** (`analisi.py`, nessuna AI): dimensioni, volume, spessori delle pareti,
   e per ogni orientamento candidato (quello del file più le pose stabili) l'area di appoggio
   e le superfici che chiedono supporti, distinguendo quelli che partono dal piatto da quelli
   che poggerebbero sul pezzo.
   Per ogni orientamento controlla anche se il pezzo **si ribalta** (baricentro fuori
   dall'impronta sul piatto) e se serve il **brim**.
   **Punteggio** (più basso = meglio): area dei supporti dal piatto + 3 × quella dei supporti
   sul pezzo + 0,02 × volume dei supporti + penalità di stabilità. Se il pezzo tocca il piatto
   solo con spigoli (meno di 10 mm²) o si ribalta, ogni problema aggiunge quanto il suo
   **ingombro sul piatto** (minimo 200): un pezzo instabile va sostenuto da brim o supporti per
   tutta la sua ombra. Pesi e soglie sono in cima ad `analisi.py`; la soglia dei supporti è in
   `config.py` (`SOGLIA_SUPPORTI`), la stessa usata dallo slicer nel sezionamento reale.
   Tra i candidati ci sono anche le scelte dell'**orientamento automatico dello slicer**
   (`orienta_slicer.py`): l'algoritmo di OrcaSlicer, da cui deriva ElegooSlicer, tradotto in
   Python, nei due modi in cui lo usa lo slicer (pulsante "Orienta" dell'interfaccia e riga di
   comando). La traduzione è stata verificata contro `elegoo-slicer.exe --orient 1`: stessi
   candidati, costi con scarto mediano 0,1%, stessa scelta. La pagina mostra chi sceglie cosa:
   nostra classifica, slicer e Claude.
2. **Immagini** (`render.py`): gli orientamenti con le sporgenze colorate
   (rosso = supporto dal piatto, arancione = supporto sul pezzo).
3. **Consiglio** (`consiglio.py`): Claude riceve numeri, immagini, stampante, scopo del pezzo
   e diario, e risponde con orientamento, materiale, impostazioni con il perché, rischi,
   un concetto da imparare e un esperimento.
4. **Diario** (`diario.py`): dopo ogni stampa annoti esito, problemi e foto; Claude può
   fare la diagnosi e le voci entrano nei consigli successivi.

Claude viene usato tramite il **Claude Agent SDK** con il login di Claude Code di questo PC
(abbonamento: nessun costo extra, conta sui limiti d'uso). Può solo leggere file: niente
comandi, niente modifiche. Per condividere lo strumento con altre persone serve invece una
chiave API (`ANTHROPIC_API_KEY`), come chiede Anthropic per i prodotti di terzi.

## Sezionamento reale con ElegooSlicer

Se ElegooSlicer è installato, ogni orientamento candidato viene **sezionato davvero** dallo slicer
(`slicer_cli.py`), con i profili di sistema indicati in `config.py` e supporti ad albero solo dal
piatto. Lo slicer non ha un'API: si usa la sua riga di comando (`--slice`, `--load-settings`,
`--load-filaments`) e si leggono i numeri nel G-code:

- **tempo** stimato dallo slicer;
- **grammi di pezzo, supporti e brim**, sommando l'estrusione di ogni tipo (`;TYPE:`) nel G-code.
  Il totale dichiarato dallo slicer è qualche decimo di grammo più alto: conta anche retrazioni e
  spurgo, che non sono materiale depositato.

I profili di sistema ereditano l'uno dall'altro (`inherits`): vengono fusi in profili completi e
lasciati marcati come "system", altrimenti la riga di comando li considera incompatibili (codice −17).
Il profilo filamento si sceglie nella barra laterale. Un orientamento si seziona in circa 2 secondi.

## Add-on augura (facoltativo)

[augura](https://github.com/pzfreo/augura) è un secondo analizzatore, basato su build123d e
OpenCASCADE. Si installa a parte, in `.venv-augura` (circa 700 MB), con
`addon_augura\installa.bat`; senza, l'assistente funziona come prima. Con l'add-on:

- si possono caricare file **STEP**: vengono convertiti in STL per l'analisi e le immagini;
- sugli STEP augura dà controlli esatti (soffitti e ponti con la loro luce, spessori,
  particolari minimi) e la sua classifica degli orientamenti;
- sugli STL i suoi controlli sarebbero approssimati (sporgenze, ribaltamento, brim) e senza
  ricerca dell'orientamento, cioè doppioni dell'analisi: per questo l'assistente lo usa **solo
  sui file STEP**.

augura non funziona senza build123d (lo importa anche per gli STL), quindi l'add-on non ha una
versione leggera. La versione è bloccata a 0.1.8 perché il progetto è pre-alpha.
Per toglierlo basta cancellare la cartella `.venv-augura`.

## Personalizzare

- `config.py`: stampante, profilo abituale, filamenti, modelli di Claude.
- `consiglio.py`: le istruzioni date a Claude e il formato della risposta.

## Dati

- `lavori/`: una cartella per ogni analisi (file, analisi.json, immagini, consiglio.md)
- `diario.jsonl` e `foto/`: il diario di stampa

## Licenze

`orienta_slicer.py` è una traduzione di codice di [OrcaSlicer](https://github.com/SoftFever/OrcaSlicer),
rilasciato sotto **AGPL-3.0**: se il progetto viene distribuito o reso pubblico, quel file (e il
programma che lo include) va distribuito con una licenza compatibile.

## Da fare

- Usare i grammi reali dei supporti nel punteggio della classifica, al posto delle aree stimate.
- Esportare il consiglio come profilo di processo da importare nello slicer.
- Riconoscere i supporti dentro le cavità (oggi risultano "dal piatto" se la cavità è aperta in basso).
