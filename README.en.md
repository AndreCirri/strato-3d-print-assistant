# 3D Printing Assistant

*[Leggi in italiano](README.md). The user interface and the code are in Italian.*

Analyses a file to print, asks Claude how to print it and explains the reason behind every choice.
It keeps a print journal, so the advice improves with experience on your own printer.

## Getting started

Double-click `avvia.bat`: the first time it creates the `.venv` environment and installs `requirements.txt`. Or by hand:

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m streamlit run app.py
```

The page opens at http://localhost:8501 and is reachable only from this PC.
The dashboard appears within a few seconds: the heavy libraries (trimesh, matplotlib, Claude Agent SDK)
are loaded only on the first analysis or the first question to Claude.

## How it works

1. **Geometric analysis** (`analisi.py`, no AI): dimensions, volume, wall thickness, and for each
   candidate orientation (the one in the file plus the stable poses) the bed contact area and the
   surfaces that need supports, distinguishing supports that start from the bed from those that
   would rest on the part.
   For each orientation it also checks whether the part **tips over** (centre of mass outside the
   footprint on the bed) and whether a **brim** is needed.
   **Score** (lower = better): area of supports from the bed + 3 × area of supports on the part
   + 0.02 × support volume + stability penalty. If the part touches the bed only with edges (less
   than 10 mm²) or tips over, each problem adds the part's **footprint on the bed** (minimum 200):
   an unstable part has to be held by brim or supports over its whole shadow. Weights and thresholds
   are at the top of `analisi.py`; the support threshold is in `config.py` (`SOGLIA_SUPPORTI`), the
   same one the slicer uses in real slicing.
   The candidates also include the choices of the **slicer's automatic orientation**
   (`orienta_slicer.py`): the OrcaSlicer algorithm, from which ElegooSlicer derives, translated into
   Python in the two modes the slicer uses it (the "Orient" button in the interface and the command
   line). The translation was checked against `elegoo-slicer.exe --orient 1`: same candidates, costs
   with a median deviation of 0.1%, same choice. The page shows who picks what: our ranking, the
   slicer and Claude.
2. **Images** (`render.py`): the orientations with overhangs coloured
   (red = support from the bed, orange = support on the part).
3. **Advice** (`consiglio.py`): Claude receives the numbers, the images, the printer, the purpose of
   the part and the journal, and answers with orientation, material, settings with their reasons,
   risks, a concept to learn and an experiment.
4. **Journal** (`diario.py`): after each print you record outcome, problems and photos; Claude can
   diagnose them, and the entries feed into later advice.

Claude is used through the **Claude Agent SDK** with the Claude Code login of this PC (subscription:
no extra cost, it counts against the usage limits). It can only read files: no commands, no changes.
To share the tool with other people an API key (`ANTHROPIC_API_KEY`) is needed instead, as Anthropic
requires for third-party products.

## Real slicing with ElegooSlicer

If ElegooSlicer is installed, every candidate orientation is **actually sliced** by the slicer
(`slicer_cli.py`), with the system profiles set in `config.py` and tree supports from the bed only.
The slicer has no API: its command line is used (`--slice`, `--load-settings`, `--load-filaments`)
and the numbers are read from the G-code:

- **time** estimated by the slicer;
- **grams of part, supports and brim**, adding up the extrusion of each type (`;TYPE:`) in the G-code.
  The total reported by the slicer is a few tenths of a gram higher: it also counts retractions and
  purge, which are not deposited material.

System profiles inherit from each other (`inherits`): they are merged into complete profiles and left
marked as "system", otherwise the command line considers them incompatible (code −17).
The filament profile is chosen in the sidebar. One orientation is sliced in about 2 seconds.

After slicing, the ranking is recomputed in **equivalent grams of support**: real grams from the
G-code, plus an estimate of the overhangs that the "bed only" profile leaves unsupported (triple
weight), 25% of the brim and a penalty for unstable orientations. The conversion used for unserved
surfaces alone is 5 g per 1,000 mm², the median of the jobs already sliced. The geometric score is
still available and is used as a fallback if the slicer is missing or fails.

On the top two orientations of the real ranking, five **process variants** are then compared:

- **Dettaglio** (detail): 0.12 mm layer, 3 walls, 20% infill;
- **Bilanciato** (balanced): the usual profile, 0.16 mm, 2 walls, 15% infill (reuses the G-code already produced);
- **Veloce** (fast): 0.24 mm layer, 2 walls, 10% infill;
- **Economico** (economy): 0.20 mm layer, 2 walls, 8% infill;
- **Robusto** (strong): 0.16 mm layer, 3 walls, 25% infill.

The dashboard shows time, material, supports and percentage changes relative to Bilanciato, then
proposes a combination consistent with the chosen priority and shows the Pareto front. Time and
material are measured; surface quality and strength are declared indicators based on layer, walls
and infill. Earlier analyses can add Economico and Robusto by reusing the slices already present.
The **progressive search** adds up to eight trials (four by default), varying one parameter at a
time around the best candidates. Layer, walls and infill stay within defined limits; orientation/
settings pairs already tried are excluded. Intermediate results can be resumed. The trade-off
normalises time, material, layer and strength indicator with 25% weights each. It is a local search:
the budget does not guarantee finding the global optimum.

Analysis, comparison, images and 3MF are processed by a separate process: you can move between tabs.
A bar refreshes every two seconds and shows percentage, phase, step counter and elapsed time.
The percentage refers to the steps completed, not the time left; you can also press
**Aggiorna avanzamento** (refresh progress). If a process stops,
**Riprendi la lavorazione** (resume) recovers the checkpoints; only invalid slices are run again.
Caches check geometry, complete profiles, filament and slicer version. Earlier results without this
information need a first recomputation. The comparison and the 3MF are invalidated when their inputs
change; an outdated configuration is not offered as an up-to-date download.

For the recommended combination you can download a **process profile JSON** importable into
ElegooSlicer and the **STL already rotated and placed on the bed**. A third button uses ElegooSlicer
to generate a **3MF project** containing the model and configurations. The profile derives from the
usual one and is exported complete with the variant and support settings used in the real comparison.
The **Configurazione da esportare** (configuration to export) menu lets you pick any valid measured
combination, with the recommended one selected at first. JSON, STL, 3MF and the spool check follow the
manual choice. The STL contains only geometry and orientation: for the same orientation it does not change
between variants. To also keep layer, walls, infill and filament, use the 3MF project.

If load type and direction are given, the dashboard also compares the component acting normal to the
layers across orientations. It is a relative indication of delamination risk, with a first suggestion
on the number of walls; it is not an FEM simulation and does not estimate the breaking load.
With the strength priority, the **Meccanico** (mechanical) process is also measured in the chosen
orientation, with the required number of walls; downloads are available only after this comparison.
Fixing and load application points can be given in file coordinates, along with constraints and the
critical zone. In bending, the beam axis comes from the two points, distinct from the force, and the
transverse lever arm is reported. Torsion compares 32 ideal shear states around the axis, showing
opening and shear on the layer plane separately. Walls and index remain heuristic: absolute stresses,
impacts or breaking loads are not computed, nor the real stress distribution due to the constraints.

The **advanced printability checks** gather in one table mesh problems, walls under two line widths,
build volume, stability, supports on the part, very tall supports and excessive support use. Risks of
collisions or trapped supports are explicitly left to be confirmed in the preview.
The **detailed checks** slice the mesh to look for closed cavities, access too narrow for a 2 mm tool,
small holes/channels, bridges with span and direction, and islands. The G-code is analysed to find
separate paths, new starts without support and travel moves under already deposited material; support
samples are compared with cavities after an estimated alignment. The report gives the section step and
the path grid, and any limit on segments or arcs not analysed. The sampled check can miss details
smaller than its resolution and does not simulate the full print head or print deformation.
Disconnected regions may be intentional.
Overlapping solids in the same STL are treated as continuous material, as the slicer does, and their
internal surfaces are not counted as overhangs to support.
Before measuring, a volumetric union is performed with manifold3d: volume, surface and thickness also
refer to the resulting material. If the bodies do not allow a reliable union, the quantitative
measurements are not shown as valid data.

The journal can also record temperatures, speeds, flow, retraction and dimensional error.
**Personal trends** appear only after at least two consistent observations for the same material:
they are readable frequencies and medians, not a model claiming to predict defects from little data.
Statistics distinguish profile and material. Parameter medians use only successful prints without
recorded defects; the proposed corrections are predefined suggestions. An empty dimensional field
means no measurement, while zero means a correct measurement. Purpose, priority and loads are saved
even without Claude.

The **Bobine** (spools) tab keeps material, colour, tare, cost and remaining grams. The remainder is
updated by subtracting a print or by entering the measured gross weight. For the recommended
configuration, the dashboard automatically says whether a compatible spool is enough and estimates
cost and remaining material. The check uses the slicer's total consumption, start-up included, and a
5% reserve. Only ready spools with a recognised material are considered; a price that was not
recorded is not shown as zero cost.

## augura add-on (optional)

[augura](https://github.com/pzfreo/augura) is a second analyser, based on build123d and OpenCASCADE.
It is disabled until you install it: from the dashboard sidebar ("Scarica e installa augura") or with
`addon_augura\installa.bat`. It goes into a separate environment, `.venv-augura` (about 700 MB);
without it, the assistant works as before. With the add-on:

- you can load **STEP** files: they are converted to STL for analysis and images;
- on STEP files augura gives exact checks (ceilings and bridges with their span, thickness, minimum
  details) and its own orientation ranking;
- on STL files its checks would be approximate (overhangs, tipping, brim) and without an orientation
  search, i.e. duplicates of the analysis: that is why the assistant uses it **only on STEP files**.

augura does not work without build123d (it imports it for STL files too), so the add-on has no light
version. The version is pinned to 0.1.8 because the project is pre-alpha.
To remove it use "Rimuovi augura" in the sidebar (or delete the `.venv-augura` folder).

## Customising

- `config.py`: printer, usual profile, filaments, Claude models.
- `consiglio.py`: the instructions given to Claude and the answer format.

## Data

- `lavori/`: one folder per analysis (file, analisi.json, images, slices, consiglio.md,
  richiesta.json with the form fields, consiglio.json with choice, model and cost).
  Every analysis can be reopened without recomputing anything: from the **Analisi passate** (past
  analyses) tab, by reloading the page (the open job stays in the address, `?lavoro=...`) or by
  loading the same file again, which is recognised by its SHA-256 fingerprint and offers to reopen
  the saved analysis.
- `diario.jsonl` and `foto/`: the print journal;
- `bobine.json`: personal spool inventory, excluded from Git.

Personal databases (`*.db`, `*.sqlite`, `*.sqlite3`), their WAL/SHM/journal files, snapshots in the root
`backup/` and `backups/` directories, logs and local credentials are excluded from Git. SQL schemas,
migrations and synthetic fixture generators remain versionable. Shared `.env.example`, `.env.sample`
and `.env.template` files must contain placeholder values only. Ignore rules do not remove files that
have already been committed or data stored in Git history.

## Data sent to Claude

Everything stays on this PC until you ask for advice or a diagnosis. Only then is the request sent to
Anthropic through the Claude Agent SDK, with **your** Claude Code login or your `ANTHROPIC_API_KEY`:
the project contains and stores no credentials.

- **Advice**: printer (`config.py`), form fields (purpose, priority, loads), the analysis as JSON
  (measurements, orientations, slicer results) and the last 15 journal entries; Claude opens the
  orientation images in the job folder with its read tool.
- **Diagnosis**: the journal entry, its photos and the other recent entries.

Claude only has the read tool (no commands, no changes) and starts from the job folder, which also holds
the model file. Claude Code's personal settings and memory are not loaded.

## License

Copyright (C) 2026 Andrea Cirrincione.

This program is free software: you can redistribute it and/or modify it under the terms of the
**GNU Affero General Public License version 3** (AGPL-3.0) as published by the Free Software
Foundation. It is distributed in the hope that it will be useful, but **without any warranty**.
The full text is in the [`LICENSE`](LICENSE) file.

In short: anyone may use, study, modify and redistribute the program, even for a fee, but modified
versions, including those offered only as a web service, must remain AGPL-3.0 with the source code
available to their users.

`orienta_slicer.py` is a Python translation of code from [OrcaSlicer](https://github.com/SoftFever/OrcaSlicer),
also released under AGPL-3.0; the original files are listed in the module header.

## To do

- Recognise supports inside cavities (today they count as "from the bed" if the cavity is open at the bottom).
