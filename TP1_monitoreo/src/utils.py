"""utils.py — Funciones auxiliares compartidas."""
import time
import json


def dump_snapshot(snapshot):
    """Guarda el snapshot actual a un archivo JSON."""
    ts = int(time.time())
    nombre = f'dump_{ts}.json'
    try:
        datos = {}
        for clave in snapshot.keys():
            datos[clave] = {
                'ts': snapshot[clave].get('ts', 0),
                'datos': str(dict(snapshot[clave].get('datos', {}))),
            }
        with open(nombre, 'w') as f:
            json.dump(datos, f, indent=2, default=str)
        return nombre
    except Exception as e:
        return f'Error: {e}'
