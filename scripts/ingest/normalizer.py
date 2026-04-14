import re

OCR_FIXES = [
    (r'^80/', 'SD '),
    (r'^SJD\s+', 'SD '),
    (r'^SO\s+', 'SD '),
    (r'^5D\s+', 'SD '),
    (r'^T0\s+', 'TD '),
    (r'^TO\s+', 'TD '),
    (r'^,AT', 'AT'),
    (r'^ATC\s+', 'AT '),
    (r'^ATOi\s+', 'AT 0'),
    (r'\s+', ' '),
    (r'/(\d{2})\s*$', r'/\1'),
]

def normalizar_codigo(codigo: str) -> str:
    if not codigo:
        return codigo
    resultado = codigo.strip()
    for patron, reemplazo in OCR_FIXES:
        resultado = re.sub(patron, reemplazo, resultado)
    return resultado.strip()

def completar_matricula(matricula_trunca: str, markdown: str) -> str:
    """
    Si la matrícula está truncada (ej T-43), busca la versión completa
    en el markdown fuente (ej T-43.822).
    """
    if not matricula_trunca:
        return matricula_trunca
    
    # Si ya tiene punto decimal, está completa
    if re.match(r'^(T\d*|RIE[^.]*)-\d+\.\d+', matricula_trunca):
        return matricula_trunca
    
    # Extrae el prefijo y número base (ej T- y 43, o T3- y 48)
    match = re.match(r'^(T\d*|RIE[^-]*)-(\d+)$', matricula_trunca)
    if not match:
        return matricula_trunca
    
    prefijo = match.group(1)
    numero_base = match.group(2)
    
    # Busca en el markdown una matrícula que empiece con ese prefijo-número
    patron_busqueda = re.escape(f"{prefijo}-{numero_base}") + r'\.\d+'
    encontradas = re.findall(patron_busqueda, markdown)
    
    if encontradas:
        # Devuelve la más frecuente (por si hay variantes)
        return max(set(encontradas), key=encontradas.count)
    
    return matricula_trunca

def normalizar_matricula(matricula: str) -> str:
    """Normaliza formato básico de matrícula"""
    if not matricula:
        return matricula
    matricula = matricula.strip()
    if re.match(r'^T\d*-\d+', matricula):
        return matricula
    match = re.search(r'T(\d*)[.\-\s](\d+[\.\d]*)', matricula)
    if match:
        prefijo = match.group(1)
        numero = match.group(2)
        if prefijo:
            return f"T{prefijo}-{numero}"
        return f"T-{numero}"
    return matricula

def normalizar_nota(nota: dict, markdown: str = "") -> dict:
    """Aplica normalización a todos los campos de una nota"""
    if 'codigo_nota' in nota:
        nota['codigo_nota'] = normalizar_codigo(nota['codigo_nota'])
    
    if 'personas' in nota:
        for persona in nota['personas']:
            if 'numero_matricula' in persona and persona['numero_matricula']:
                mat = normalizar_matricula(persona['numero_matricula'])
                if markdown:
                    mat = completar_matricula(mat, markdown)
                persona['numero_matricula'] = mat
    
    if 'resoluciones_distritales' in nota:
        for res in nota['resoluciones_distritales']:
            if 'matricula' in res and res['matricula']:
                mat = normalizar_matricula(res['matricula'])
                if markdown:
                    mat = completar_matricula(mat, markdown)
                res['matricula'] = mat
    
    return nota
