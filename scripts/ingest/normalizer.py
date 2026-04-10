import re

# Patrones conocidos de errores OCR en códigos de notas
OCR_FIXES = [
    # SD mal reconocido
    (r'^80/', 'SD '),
    (r'^SJD\s+', 'SD '),
    (r'^SO\s+', 'SD '),
    (r'^5D\s+', 'SD '),
    # TD mal reconocido  
    (r'^T0\s+', 'TD '),
    (r'^TO\s+', 'TD '),
    # AT mal reconocido
    (r'^,AT', 'AT'),
    (r'^ATC\s+', 'AT '),
    (r'^ATOi\s+', 'AT 0'),
    # Separadores y espacios
    (r'\s+', ' '),
    # Caracteres basura al final del año
    (r'/(\d{2})\s*$', r'/\1'),
]

def normalizar_codigo(codigo: str) -> str:
    if not codigo:
        return codigo
    
    resultado = codigo.strip()
    for patron, reemplazo in OCR_FIXES:
        resultado = re.sub(patron, reemplazo, resultado)
    
    return resultado.strip()

def normalizar_matricula(matricula: str) -> str:
    """Normaliza números de matrícula al formato T-XXXXX o T3-XXXXX"""
    if not matricula:
        return matricula
    
    matricula = matricula.strip()
    # Ya tiene formato correcto
    if re.match(r'^T\d*-\d+$', matricula):
        return matricula
    
    # Intenta reconstruir
    match = re.search(r'T(\d*)[.\-\s](\d+)', matricula)
    if match:
        prefijo = match.group(1)
        numero = match.group(2)
        if prefijo:
            return f"T{prefijo}-{numero}"
        return f"T-{numero}"
    
    return matricula

def normalizar_nota(nota: dict) -> dict:
    """Aplica normalización a todos los campos de una nota"""
    if 'codigo_nota' in nota:
        nota['codigo_nota'] = normalizar_codigo(nota['codigo_nota'])
    
    if 'personas' in nota:
        for persona in nota['personas']:
            if 'numero_matricula' in persona and persona['numero_matricula']:
                persona['numero_matricula'] = normalizar_matricula(
                    persona['numero_matricula']
                )
    
    if 'resoluciones_distritales' in nota:
        for res in nota['resoluciones_distritales']:
            if 'matricula' in res and res['matricula']:
                res['matricula'] = normalizar_matricula(res['matricula'])
    
    return nota
