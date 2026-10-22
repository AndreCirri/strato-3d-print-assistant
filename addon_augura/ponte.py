"""Gira dentro l'ambiente dell'add-on (.venv-augura), che ha build123d.

Uso: python ponte.py step2stl <file.step> <file.stl>
"""
import sys

from build123d import export_stl, import_step


def step2stl(step, stl):
    forma = import_step(step)
    # tolleranza fine: l'STL serve all'analisi e alle immagini dell'assistente
    export_stl(forma, stl, tolerance=0.01, angular_tolerance=0.1)


if __name__ == "__main__":
    comando, *argomenti = sys.argv[1:]
    {"step2stl": step2stl}[comando](*argomenti)
