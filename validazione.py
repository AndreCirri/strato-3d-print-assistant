import math


def numero(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def risultato_valido(r):
    return (not r.get("errore") and numero(r.get("tempo_s")) and r["tempo_s"] > 0
            and all(numero(r.get(k)) and r[k] >= 0 for k in ("pezzo_g", "supporti_g", "brim_g"))
            and r["pezzo_g"] > 0)


def riga_valida(r):
    return (not r.get("errore") and numero(r.get("tempo_s")) and r["tempo_s"] > 0
            and numero(r.get("materiale_g")) and r["materiale_g"] > 0)
