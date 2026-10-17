import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

import procfs


def test_infiere_tipo_de_fd():
    assert procfs.tipo_fd('socket:[42]') == 'socket'
    assert procfs.tipo_fd('pipe:[42]') == 'pipe'
    assert procfs.tipo_fd('/dev/pts/2') == 'tty'
    assert procfs.tipo_fd('/tmp/datos') == 'file'


def test_threads_del_proceso_actual_incluyen_tid_y_estado():
    threads = procfs.leer_threads(__import__('os').getpid())
    assert threads
    assert {'tid', 'nombre', 'state', 'utime', 'stime'} <= threads[0].keys()


def test_status_actual_expone_memoria_y_cambios_de_contexto():
    status = procfs.leer_status(__import__('os').getpid())
    assert status is not None
    assert {'vm_data', 'vm_stk', 'vm_exe', 'vm_lib', 'vm_swap',
            'voluntary_ctxt_switches', 'nonvoluntary_ctxt_switches'} <= status.keys()
