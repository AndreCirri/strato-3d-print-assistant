# Correzioni dalla revisione critica

Ogni fix deve avere verifica mirata e descrizione. Dopo G01, i fix sono raccolti in un commit finale come richiesto dall'utente.

## Priorità alta

- [x] G01 — Sottrarre solo la porzione di faccia coperta dai solidi sovrapposti. Verificati copertura totale, parziale, più corpi e vuoto reale; il contenitore resta correttamente in posa 3. Le aree sono calcolate sottraendo sezioni planari; distanza e tipo di supporto restano stimati tramite un punto rappresentativo della porzione esposta. La colorazione delle immagini resta per triangolo.
- [x] C01 — Impronta di STL, macchina, processo completo, filamento, eseguibile/motore slicer e parser; hash del G-code. I vecchi risultati senza impronta devono essere verificati ricalcolando.
- [x] E01 — Il 3MF è scaricabile soltanto se la sua impronta e il suo hash corrispondono agli input attuali. Archivio verificato dopo la generazione.
- [x] M01 — Per robustezza con carico dichiarato si misura una variante Meccanico con le pareti richieste sull'orientamento indicato. Raccomandazione e download restano bloccati finché il confronto non soddisfa questi requisiti.

## Priorità media

- [x] R01 — Il pulsante di ripetizione passa dal controllo cache: soltanto i risultati falliti o incompatibili vengono risezionati.
- [x] R02 — Parser e raccomandazione rifiutano tempi nulli/non finiti, materiale mancante e G-code incompleti; controllo anche nella classifica reale.
- [x] D01 — Campo dimensionale inizialmente vuoto; lo zero è una misura valida nella mediana. Le vecchie annotazioni che usavano zero anche come valore predefinito restano ambigue e vanno corrette manualmente.
- [x] B01 — Disponibilità sul consumo totale (avvio incluso) con riserva del 5%; costo sul consumo; esclusione di materiali sconosciuti e bobine non pronte. Costo non annotato mostrato come non disponibile.
- [x] B02 — ID della bobina incluso nelle etichette dei menu.
- [x] P01 — Richiesta salvata prima dei calcoli e a ogni modifica dei widget; ripristino completo con valori iniziali per i campi assenti nelle analisi vecchie.
- [x] U01 — Analisi, confronto, immagini e 3MF eseguiti in un worker separato. Stato persistente, lock contro doppi avvii, scritture atomiche e ripresa tramite checkpoint e cache. Dopo il riavvio del PC serve premere Riprendi; i G-code validi restano riutilizzabili.

## Funzionalità ancora parziali

- [ ] O01 — Ricerca progressiva dei parametri oltre i cinque preset fissi; esplicitare pesi e indicatori della frontiera Pareto.
- [ ] M02 — Raccogliere fissaggi e zona caricata; rivedere le euristiche per flessione e torsione e i suggerimenti sulle pareti.
- [ ] S01 — Implementare veri controlli di cavità/supporti intrappolati, ponti, fori, isole e collisioni del toolpath.
- [x] D02 — Tendenze filtrate per materiale e profilo; mediane dei parametri solo su stampe riuscite senza problemi. Le correzioni sono esplicitamente predefinite; i vecchi record senza profilo restano nel gruppo non annotato.
- [ ] G02 — Estendere il trattamento dei solidi sovrapposti a spessori, volumi e altri indicatori geometrici.

## Verifiche

Regressioni in `test_fix_revisione.py`, oltre ai test esistenti. Prova reale ripetibile con `.venv/Scripts/python.exe verifiche/integrazione_worker.py`: directory temporanea isolata, slicer reale, navigazione durante il lavoro, ripresa, persistenza senza Claude, vincoli meccanici e 3MF con 5 pareti. Le voci evolutive O01/M02/S01/G02 restano aperte: non sono implementate da questi fix.
