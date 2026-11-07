# Revisione tecnica

Registro delle correzioni completate durante la revisione tecnica. Non rappresenta una roadmap;
le limitazioni riportate descrivono il perimetro delle funzionalità implementate.


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

- [x] O01 — Ricerca locale progressiva oltre i preset, con budget 0–8 prove, una modifica per candidato, esclusione delle coppie già provate e checkpoint intermedi. Limiti: layer 0,12–0,28, pareti 2–5, infill 5–35%. Pesi del compromesso espliciti al 25%; l'esplorazione è locale e non garantisce l'ottimo globale.
- [x] M02 — Fissaggio e applicazione del carico in coordinate del file, descrizione dei vincoli e della zona critica persistite. Flessione lungo l'asse fissaggio–carico e braccio trasversale; torsione mediante 32 stati di taglio ideali. Apertura/taglio sul piano layer distinti, regole sulle pareti dichiarate ed avvisi sulle pareti fisicamente realizzabili. Restano esclusi FEM, urti, tensioni assolute e carichi di rottura.
- [x] S01 — Sezioni orizzontali con connettività dell'aria libera per cavità chiuse e accesso utensile da 2 mm; fori/canali stretti, ponti con luce/direzione e nuove isole. Nel G-code: estrusione relativa/assoluta, archi I/J, componenti dei percorsi, inizi senza appoggio e viaggi sotto materiale già depositato. Campioni di supporto allineati al modello per stimare supporti in cavità chiuse. Controlli campionati, con limiti e copertura parziale mostrati; non certificano collisioni della testina completa o estrazione fisica dei supporti.
- [x] D02 — Tendenze filtrate per materiale e profilo; mediane dei parametri solo su stampe riuscite senza problemi. Le correzioni sono esplicitamente predefinite; i vecchi record senza profilo restano nel gruppo non annotato.
- [x] G02 — Unione volumetrica con manifold3d prima di analisi, orientamenti e slicing. Volume, superficie e spessori escludono le superfici interne; registrate le informazioni originali. Se l'unione non è affidabile, i valori quantitativi non vengono dichiarati. Sul contenitore: volume unito 32,541 cm³ rispetto a 41,834 cm³ di somma dei due corpi; p5 dello spessore 1 mm anziché 0,02 mm.

## Verifiche

Regressioni in `tests/test_fix_revisione.py`, `tests/test_ricerca.py`, `tests/test_analisi.py`, `tests/test_resistenza.py` e `tests/test_controlli_dettagliati.py`, oltre ai test esistenti. Prova reale ripetibile con `.venv/Scripts/python.exe tests/integrazione_worker.py`: directory temporanea isolata, slicer reale, navigazione durante il lavoro, ripresa, persistenza senza Claude, vincoli meccanici e 3MF con 5 pareti. Le funzionalità sono implementate nei limiti descritti sopra; gli indicatori euristici non equivalgono a simulazioni strutturali o certificazioni di stampabilità.
