# Computación II — Lucas Valdemoros

Repositorio de trabajos prácticos · Universidad de Mendoza · 2026.

| Trabajo | Descripción | Documentación |
| --- | --- | --- |
| TP1 | Monitor de procesos y threads en Linux. | [TP1_monitoreo](TP1_monitoreo/README.md) |
| TP2 | API para encolar, ejecutar y cancelar tareas. | [TP2_tareas](TP2_tareas/README.md) |

## TP2

Desde la raíz del repositorio:

```bash
docker compose up --build
```

API en `http://127.0.0.1:8000`; documentación interactiva en `http://127.0.0.1:8000/docs`.

## TP1

Desde la raíz, en una terminal interactiva:

```bash
docker compose --profile tp1 run --build --rm monitor
```

Para ejecutarlo directamente con Python en Linux/WSL, consultar las [instrucciones del TP1](TP1_monitoreo/README.md#ejecución).
