"""Avanzamento persistente: percentuale di passaggi, non stima del tempo residuo."""
import os
import time
from persistenza import salva_json


class Avanzamento:
    def __init__(self, cartella, modo):
        self.percorso = cartella / 'lavorazione.json'
        self.modo = modo
        self.inizio = time.time()
        self.frazione = 0.

    def aggiorna(self, fase, frazione=None, completati=None, totale=None):
        if frazione is not None:
            self.frazione = max(self.frazione, min(.99, max(0., float(frazione))))
        salva_json(self.percorso, {'stato': 'in corso', 'pid': os.getpid(), 'modo': self.modo,
                                   'fase': fase, 'frazione': self.frazione,
                                   'completati': completati, 'totale': totale, 'inizio': self.inizio})

    def termina(self, errore=None):
        salva_json(self.percorso, {'stato': 'errore' if errore else 'completata', 'pid': os.getpid(),
                                   'modo': self.modo, 'fase': str(errore) if errore else 'Completata',
                                   'errore': str(errore) if errore else None,
                                   'frazione': self.frazione if errore else 1., 'inizio': self.inizio})
