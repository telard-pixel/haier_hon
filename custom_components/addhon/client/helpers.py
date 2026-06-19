"""Utility numeriche del client hOn nativo.

Primo "mattone" portato da pyhOn col loop di migrazione (characterization +
differential test vs `_vendor/pyhon/helper.py`). Per ora nessun consumatore di
produzione: i chiamanti di `str_to_float` sono ancora interni a pyhOn (range.py/
enum.py); questa funzione verrà usata quando porteremo il parser. Tenuta a
comportamento IDENTICO a pyhOn (il differential test lo verifica), così quando il
parser passerà a usarla non cambia nulla.
"""
from __future__ import annotations


def str_to_float(value: str | float) -> float:
    """Converte un valore hOn (di solito stringa) in numero.

    Comportamento (identico a pyhOn, verificato col differential test):
    - prova `int(value)` per primo: "5"->5, "-16"->-16, 5->5;
    - in caso di ValueError ricade su `float`, normalizzando la virgola
      decimale: "5.5"->5.5, "5,5"->5.5.

    QUIRK noto e VOLUTAMENTE preservato: `int()` viene tentato anche sui float,
    e `int(5.5)` TRONCA a 5 senza errore (cattura solo ValueError, non gli altri).
    Quindi va passata una STRINGA per preservare i decimali ("5.5"), mai un float
    (5.5 -> 5). È la ragione per cui number.py invia i setpoint come stringa.
    Inoltre input non numerici (es. "abc", None) propagano l'eccezione originale
    (ValueError / TypeError): non vengono mascherati.
    """
    try:
        return int(value)
    except ValueError:
        return float(str(value).replace(",", "."))
