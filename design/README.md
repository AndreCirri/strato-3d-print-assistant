# Design STRATO

Il file sorgente da aprire in FigCraft è **strato-ui.figcraft** in questa cartella.
Contiene la pagina dei mockup, il lavoro personalizzato «STRATO · Caricato», la
pagina **Componenti**, i master, le varianti e le istanze collegate. Il documento
include anche il checkpoint «Prima del riuso componenti».

## Riprendere su un altro PC

1. Recupera il branch `feature/ui-redesign` e aggiorna il checkout.
2. Installa FigCraft desktop, se non è già disponibile.
3. Apri `design/strato-ui.figcraft`. Non occorre importare JSON o ricostruire il design.
4. Installa il font **Plus Jakarta Sans** da `assets/PlusJakartaSans-Variable.ttf`
   per visualizzare la tipografia corretta in FigCraft. La licenza è in
   `assets/PlusJakartaSans-OFL.txt`. L'app Python incorpora già il font locale.
5. Per l'app: aggiorna l'ambiente con `python -m pip install -r requirements.txt`
   (nell'ambiente virtuale del progetto) e avvia `avvia.bat`.

## MCP nativo e documento aperto

Su Windows, `design/avvia-figcraft-live.cmd` apre il file di questa repo con il
canale di controllo locale sulla porta 7979. Cerca FigCraft nel percorso standard
di Program Files e poi nell'installazione locale; puoi impostare `FIGCRAFT_EXE`
al percorso completo dell'app.

Nel client MCP, configura come server STDIO:

```text
command: C:\Program Files\ArtCraft\FigCraft\figcraft-cli.exe
args:    mcp --attach 7979
```

Se usi Codex CLI e FigCraft è installato nel percorso standard:

```powershell
codex mcp add figcraft-live -- "C:\Program Files\ArtCraft\FigCraft\figcraft-cli.exe" mcp --attach 7979
```

Adatta soltanto il percorso dell'eseguibile se l'installazione è diversa.
La configurazione MCP e il login del client sono locali al PC e non sono inclusi
nel repository. Il collegamento attached modifica lo stesso documento mostrato
nella finestra FigCraft; `mcp` senza `--attach` apre una sessione separata.

## Stato del lavoro

- La schermata di caricamento è implementata nell'app, con Plus Jakarta Sans locale.
- Sono stati rimossi dall'app il pannello «Parametri di importazione» e il badge «Attivo».
- Gli altri nove passaggi/sezioni sono mockup modificabili, non ancora tutti implementati.
- I mockup usano 108 istanze nei 11 frame, più le istanze dimostrative nella pagina Componenti.
- Intestazioni, navigazione, fasi, pulsanti e campi sono collegati a master condivisi;
  modelli e contenuti specifici restano livelli nativi.
- Il percorso superiore della prima schermata è stato ripristinato senza badge «ATTIVO».
- Per tutte le nuove icone UI, scegliere esclusivamente set di Icons8; il set finale
  non è ancora stato scelto. Logo e illustrazioni geometriche sono elementi del design.

Il font dell'interfaccia è **Plus Jakarta Sans ovunque**. Le indicazioni Geist,
Inter e JetBrains Mono del documento Stitch originale sono superate.

Le anteprime in `design/previews/` servono a consultare rapidamente il lavoro;
il file `.figcraft` è la fonte modificabile. `design/review/` conserva il confronto
visivo e la verifica del riuso dei componenti. Nel confronto con l'app, FigCraft
segnalava il font mancante e rendeva un sostituto: il confronto dei glifi non era
quindi perfettamente omogeneo.

## Riferimento iniziale

`design/reference/stitch/` contiene HTML e immagine forniti nello ZIP iniziale.
È materiale di riferimento storico; per layout, copy e componenti aggiornati usare
il documento FigCraft. L'HTML originale può richiedere risorse esterne.
