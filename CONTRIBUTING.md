# Contributing to STRATO

The interface and most source identifiers are Italian. Issues and pull requests are welcome
in Italian or English. Describe the problem, expected behaviour and steps to reproduce it.
Use synthetic models and remove personal information from screenshots and logs.

## Development

Use Windows and Python 3.12, the currently tested platform:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m streamlit run app.py
```

Work on a branch. Keep changes focused, follow existing code conventions and explain relevant
limitations. Add meaningful tests when changing analysis, persistence or export behaviour.

## Verification

```powershell
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe -m unittest discover -q
```

Unit tests use synthetic profiles and do not require ElegooSlicer, Claude credentials or augura.
GitHub Actions runs this suite on Windows with Python 3.12.

For the optional end-to-end worker test, install ElegooSlicer with the profiles in `config.py`,
configure its paths as described in the README, then run:

```powershell
.venv\Scripts\python.exe verifiche/integrazione_worker.py
```

This test generates a model in a temporary directory, invokes the real slicer, checks cached
results and a mechanical 3MF export. It skips explicitly when the slicer is unavailable.
For UI changes, also check the app in a browser at desktop and smaller sizes.

Do not commit models, journals, inventories, credentials or generated analysis directories.
Report vulnerabilities according to [SECURITY.md](SECURITY.md).
Contributions are distributed under the repository's [AGPL-3.0 license](LICENSE).
