# Assistente di stampa 3D

Analizza un file da stampare, chiede a Claude come stamparlo e spiega il perché di ogni scelta.
Tiene un diario delle stampe, così i consigli migliorano con l'esperienza sulla tua stampante.

## Avvio

Doppio clic su `avvia.bat`, oppure:

```
python -m streamlit run app.py
```

La pagina si apre su http://localhost:8501 ed è raggiungibile solo da questo PC.

## Come funziona

1. **Analisi geometrica** (`analisi.py`, nessuna AI): dimensioni, volume, spessori delle pareti,
   e per ogni orientamento candidato (quello del file più le pose stabili) l'area di appoggio
   e le superfici che chiedono supporti, distinguendo quelli che partono dal piatto da quelli
   che poggerebbero sul pezzo.
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

## Personalizzare

- `config.py`: stampante, profilo abituale, filamenti, modelli di Claude.
- `consiglio.py`: le istruzioni date a Claude e il formato della risposta.

## Dati

- `lavori/`: una cartella per ogni analisi (file, analisi.json, immagini, consiglio.md)
- `diario.jsonl` e `foto/`: il diario di stampa

## Da fare

- Far sezionare gli orientamenti migliori a ElegooSlicer/OrcaSlicer da riga di comando
  per avere tempi, filamento e supporti reali invece delle stime.
- Esportare il consiglio come profilo di processo da importare nello slicer.
- Riconoscere i supporti dentro le cavità (oggi risultano "dal piatto" se la cavità è aperta in basso).
