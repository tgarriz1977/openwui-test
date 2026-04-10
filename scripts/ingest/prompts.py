PROMPT_METADATOS_Y_ME = """
Sos un extractor de datos estructurados especializado en actas del Colegio de Técnicos de la Provincia de Buenos Aires.

Se te provee el contenido completo de un acta en formato Markdown. Tu tarea es extraer ÚNICAMENTE los datos indicados y devolverlos como JSON válido, sin texto adicional, sin bloques de código, sin explicaciones.

Extraé los siguientes datos:

1. METADATOS DEL ACTA:
- acta_numero (integer): número del acta
- fecha (string YYYY-MM-DD): fecha de la sesión
- participantes (array de strings): nombres completos de los participantes
- hora_inicio (string HH:MM): hora de inicio
- hora_fin (string HH:MM): hora de finalización
- total_paginas (integer): total de páginas

2. NOTAS INGRESADAS ME: todas las filas de la tabla bajo "NOTAS INGRESADAS ME"
3. NOTAS INGRESADAS MT: todas las filas bajo "NOTAS INGRESADAS MT" (puede estar vacía)

Para cada nota extraé:
- codigo_nota (string): código de la nota, ej "Me 16.859/24"
- seccion (string): "ME" o "MT"
- tema (string): tema o asunto de la nota
- fecha_nota (string YYYY-MM-DD o null): fecha dentro de la celda de tema si existe
- descripcion (string): texto completo de la descripción
- resolucion (string o null): texto de la resolución si existe
- personas (array): cada persona mencionada con:
  - nombre_completo (string)
  - numero_matricula (string o null): formato T-XXXXX o T3-XXXXX
  - rol_mencion (string): "solicitante", "involucrado", o "cancelacion"
- expedientes (array): cada expediente mencionado con:
  - numero_expediente (string)
  - referencia_ctd (string o null)

Devolvé ÚNICAMENTE este JSON, sin nada más:
{
  "acta": {
    "acta_numero": ...,
    "fecha": "...",
    "participantes": [...],
    "hora_inicio": "...",
    "hora_fin": "...",
    "total_paginas": ...
  },
  "notas_me_mt": [
    {
      "codigo_nota": "...",
      "seccion": "...",
      "tema": "...",
      "fecha_nota": "...",
      "descripcion": "...",
      "resolucion": "...",
      "personas": [...],
      "expedientes": [...]
    }
  ]
}

CONTENIDO DEL ACTA:
{markdown}
"""

PROMPT_DISTRITOS_Y_RESTO = """
Sos un extractor de datos estructurados especializado en actas del Colegio de Técnicos de la Provincia de Buenos Aires.

Se te provee el contenido completo de un acta en formato Markdown. Tu tarea es extraer ÚNICAMENTE los datos indicados y devolverlos como JSON válido, sin texto adicional, sin bloques de código, sin explicaciones.

Extraé los siguientes datos:

1. NOTAS POR DISTRITO: todas las filas de las tablas bajo "DISTRITO I" hasta "DISTRITO VII"
Para cada nota extraé:
- codigo_nota (string): código de la nota, ej "SD 3.588/24"
- seccion (string): nombre del distrito, ej "Distrito I", "Distrito II", etc
- tema (string): tema o asunto
- fecha_nota (string YYYY-MM-DD o null)
- descripcion (string): texto completo
- resolucion (string o null)
- personas (array): cada persona con nombre_completo, numero_matricula, rol_mencion
- expedientes (array): expedientes mencionados
- resoluciones_distritales (array): cada resolución distrital mencionada con:
  - numero_resolucion (string): ej "RES.DIIN°1.708/24"
  - tecnico (string): nombre del técnico
  - matricula (string): número de matrícula
  - tipo_resolucion (string): "Cancelacion", "Rehabilitacion", u otro
  - distrito (string): distrito al que pertenece

2. NOTAS AS: todas las filas bajo "NOTAS AS"
Para cada nota extraé los mismos campos que arriba (sin resoluciones_distritales)

3. NOTAS AT: todas las filas bajo "NOTAS AT"
Para cada nota extraé los mismos campos básicos

4. TEMAS VARIOS: cada punto numerado bajo "TEMAS VARIOS"
Para cada punto extraé:
- numero_punto (integer)
- titulo (string)
- descripcion (string)
- resolucion (string o null)

Devolvé ÚNICAMENTE este JSON, sin nada más:
{
  "notas_distritos": [...],
  "notas_as": [...],
  "notas_at": [...],
  "temas_varios": [
    {
      "numero_punto": ...,
      "titulo": "...",
      "descripcion": "...",
      "resolucion": "..."
    }
  ]
}

CONTENIDO DEL ACTA:
{markdown}
"""
