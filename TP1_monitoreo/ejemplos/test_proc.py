def leer_stat(pid):
    with open(f'/proc/{pid}/stat', 'r') as f:
        linea = f.read()

    inicio_nombre = linea.find('(')
    fin_nombre = linea.rfind(')')

    pid_str = linea[:inicio_nombre].strip()
    nombre = linea[inicio_nombre+1:fin_nombre]

    resto = linea[fin_nombre+2:].split()

    return {
        'pid': int(pid_str),
        'nombre': nombre,
        'estado': resto[0],
        'ppid': int(resto[1]),
        'utime': int(resto[11]),
        'stime': int(resto[12]),
    }


if __name__ == '__main__':
    import os
    print(leer_stat(os.getpid()))

