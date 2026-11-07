"""Riepilogo della copertura per gli artifact e il job summary di GitHub Actions."""
import json
import os
from pathlib import Path


def riepilogo(dati):
    totale = dati['totals']
    righe = [
        '# Copertura dei test', '',
        f"Copertura complessiva (righe e rami): **{totale['percent_covered']:.1f}%**. "
        f"Righe: {totale['covered_lines']}/{totale['num_statements']}; "
        f"rami: {totale['covered_branches']}/{totale['num_branches']}.", '',
        'La misura riguarda la suite unittest su Windows/Python 3.12. '
        'Include anche i moduli mai eseguiti; esclude test, strumenti di verifica e dati locali. '
        'Le chiamate simulate misurano il codice attraversato, non il funzionamento dei servizi esterni.', '',
        '## Moduli, dai meno coperti', '',
        '| Modulo | Righe e rami | Righe mancanti | Rami mancanti |',
        '|---|---:|---:|---:|',
    ]
    ordinati = sorted(dati['files'].items(),
                      key=lambda item: (item[1]['summary']['percent_covered'], item[0]))
    for nome, dettagli in ordinati:
        s = dettagli['summary']
        righe.append(f"| `{nome}` | {s['percent_covered']:.1f}% | "
                     f"{s['missing_lines']} | {s['missing_branches']} |")
    righe += ['', '## Aree da approfondire', '']
    for nome, dettagli in ordinati:
        s = dettagli['summary']
        if s['num_statements'] and s['percent_covered'] < 50:
            righe.append(f"- `{nome}`: {s['percent_covered']:.1f}% di copertura; "
                         f"{s['missing_lines']} righe e {s['missing_branches']} rami non esercitati.")
    if not any(d['summary']['num_statements'] and d['summary']['percent_covered'] < 50
               for _, d in ordinati):
        righe.append('- Nessun modulo sotto il 50%; consultare comunque le righe e i rami mancanti.')
    righe += [
        '', 'Il 50% serve solo a evidenziare le aree meno coperte: non blocca la CI. '
        'Il report HTML indica tutte le righe e i rami mancanti.', '',
        '## Verifiche fuori da questa misura', '',
        '- Layout, responsive, upload dal browser e rendering WebGL: manca una suite browser in CI.',
        '- ElegooSlicer e progetto 3MF reali: la suite usa fixture; '
        '`verifiche/integrazione_worker.py` resta una verifica opzionale separata.',
        '- Claude e conversione STEP con augura reali: non vengono invocati dalla CI.',
        '', 'Scaricare l\'artifact `coverage-report`: aprire `html/index.html` per i dettagli. '
        'Sono disponibili anche JSON e XML per strumenti esterni.', '',
    ]
    return '\n'.join(righe)


def main():
    cartella = Path('coverage')
    rapporto = riepilogo(json.loads((cartella / 'coverage.json').read_text(encoding='utf-8')))
    (cartella / 'summary.md').write_text(rapporto, encoding='utf-8')
    print(rapporto)
    if destinazione := os.environ.get('GITHUB_STEP_SUMMARY'):
        with Path(destinazione).open('a', encoding='utf-8') as file:
            file.write(rapporto)


if __name__ == '__main__':
    main()
