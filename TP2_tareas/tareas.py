"""I/O cooperativo y cálculo fuera del loop: clases 20 y 21."""
import asyncio
import hashlib
import time

import httpx


def hash_lote(dato: bytes, iteraciones: int) -> bytes:
    """Función de módulo serializable; cada iteración usa el digest anterior."""
    for _ in range(iteraciones):
        dato = hashlib.sha256(dato).digest()
    return dato


async def hashear(pedido, pool, lote):
    dato = pedido.texto.encode('utf-8')
    pendientes = pedido.iteraciones
    loop = asyncio.get_running_loop()
    while pendientes:
        cantidad = min(lote, pendientes)
        futuro = loop.run_in_executor(pool, hash_lote, dato, cantidad)
        try:
            dato = await asyncio.shield(futuro)
        except asyncio.CancelledError:
            # Cancelar el await NO detiene el proceso. Recogemos el lote activo
            # antes de propagar la cancelación; nunca se envía el siguiente.
            while not futuro.done():
                try:
                    await asyncio.shield(futuro)
                except asyncio.CancelledError:
                    continue
            futuro.result()  # recoge también una excepción del proceso
            raise
        pendientes -= cantidad
    return {'hash': dato.hex(), 'iteraciones': pedido.iteraciones, 'algoritmo': 'sha256'}


async def descargar(pedido, cliente, semaforo):
    async def una(url):
        async with semaforo:
            inicio = time.perf_counter()
            resultado = {'url': str(url), 'estado_http': None, 'bytes': 0,
                         'segundos': 0, 'error': None}
            try:
                async with cliente.stream('GET', str(url)) as respuesta:
                    resultado['estado_http'] = respuesta.status_code
                    async for bloque in respuesta.aiter_bytes():
                        resultado['bytes'] += len(bloque)
            except httpx.HTTPError as exc:
                resultado['error'] = f'{type(exc).__name__}: {exc}'
            resultado['segundos'] = time.perf_counter() - inicio
            return resultado

    # Los errores de transporte esperados se convierten en resultados por URL.
    # Si ocurre un error de programación, TaskGroup recoge las hermanas.
    async with asyncio.TaskGroup() as grupo:
        descargas = [grupo.create_task(una(url)) for url in pedido.urls]
    return [t.result() for t in descargas]
