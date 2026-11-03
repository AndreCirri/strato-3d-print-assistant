# Correzioni dalla revisione critica

Ogni fix deve avere verifica mirata, descrizione e commit dedicato.

## Priorità alta

- [x] G01 — Sottrarre solo la porzione di faccia coperta dai solidi sovrapposti. Verificati copertura totale, parziale, più corpi e vuoto reale; il contenitore resta correttamente in posa 3. Le aree sono calcolate sottraendo sezioni planari; distanza e tipo di supporto restano stimati tramite un punto rappresentativo della porzione esposta. La colorazione delle immagini resta per triangolo.
- [ ] C01 — Validare la cache con geometria, macchina, processo completo, filamento e versione slicer; rifiutare G-code incompleti.
- [ ] E01 — Invalidare il 3MF esportato quando cambia una delle configurazioni o la geometria.
- [ ] M01 — Riconciliare analisi meccanica, raccomandazione principale e impostazioni esportate.

## Priorità media

- [ ] R01 — Consentire di riprovare i singoli sezionamenti falliti senza ripetere quelli validi.
- [ ] R02 — Rifiutare risultati con tempo zero, dati mancanti o G-code incompleto prima della raccomandazione.
- [ ] D01 — Distinguere misure assenti da errore dimensionale zero; includere gli zeri nella mediana.
- [ ] B01 — Calcolare disponibilità e costo sul consumo totale con margine; gestire materiale sconosciuto e stato della bobina.
- [ ] B02 — Usare ID univoci nei menu delle bobine anche con nome e residuo uguali.
- [ ] P01 — Salvare scopo, priorità e carichi anche senza una risposta di Claude; ripristinare i valori del lavoro aperto.
- [ ] U01 — Rendere riprendibili le operazioni lunghe senza dipendere dalla singola esecuzione di Streamlit.

## Funzionalità ancora parziali

- [ ] O01 — Ricerca progressiva dei parametri oltre i cinque preset fissi; esplicitare pesi e indicatori della frontiera Pareto.
- [ ] M02 — Raccogliere fissaggi e zona caricata; rivedere le euristiche per flessione e torsione e i suggerimenti sulle pareti.
- [ ] S01 — Implementare veri controlli di cavità/supporti intrappolati, ponti, fori, isole e collisioni del toolpath.
- [ ] D02 — Separare materiali/profili e stampe riuscite/fallite nelle statistiche; non presentare correzioni predefinite come correlazioni apprese.
- [ ] G02 — Estendere il trattamento dei solidi sovrapposti a spessori, volumi e altri indicatori geometrici.

## Verifiche

I 24 test presenti alla revisione passano, ma non coprono i casi sopra. Aggiungere regressioni mirate insieme ai fix; verificare la dashboard quando cambia il flusso utente.
