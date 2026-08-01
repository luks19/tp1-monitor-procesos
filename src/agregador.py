"""
agregador.py — Snapshot global compartido entre todos los procesos.
Usa multiprocessing.Manager para que cualquier proceso pueda leer/escribir.
"""
import time
from multiprocessing import Manager


def crear_snapshot(manager):
    """
    Crea el diccionario compartido con la estructura inicial del snapshot.
    Cada clave tiene un subdiccionario con 'datos' y 'ts' (timestamp).
    """
    return manager.dict({
        'resumen':    manager.dict({'datos': manager.dict(), 'ts': 0.0}),
        'memoria':    manager.dict({'datos': manager.dict(), 'ts': 0.0}),
        'fds':        manager.dict({'datos': manager.dict(), 'ts': 0.0}),
        'threads':    manager.dict({'datos': manager.dict(), 'ts': 0.0}),
        'senales':    manager.dict({'datos': manager.dict(), 'ts': 0.0}),
        'scheduling': manager.dict({'datos': manager.dict(), 'ts': 0.0}),
        'sistema':    manager.dict({'datos': manager.dict(), 'ts': 0.0}),
    })
