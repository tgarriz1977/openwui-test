import requests
import json
from openai import OpenAI
from prompts import (
    PROMPT_METADATOS_Y_ME,
    PROMPT_DISTRITOS_1_4,
    PROMPT_DISTRITOS_5_7,
    PROMPT_AS_AT,
    PROMPT_TEMAS_VARIOS
)
from normalizer import normalizar_nota
import os
from dotenv import load_dotenv

load_dotenv()


def _reparar_json(texto: str):
    """Intenta reparar JSON truncado cerrando arrays/objetos abiertos."""
    # Eliminar trailing comma o contenido parcial después del último elemento completo
    texto = texto.rstrip()
    # Cortar en el último cierre válido de objeto
    for i in range(len(texto) - 1, -1, -1):
        if texto[i] in ('}', ']'):
            truncado = texto[:i + 1]
            # Contar brackets abiertos vs cerrados
            abrir_obj = truncado.count('{') - truncado.count('}')
            abrir_arr = truncado.count('[') - truncado.count(']')
            if abrir_obj >= 0 and abrir_arr >= 0:
                cierre = ']' * abrir_arr + '}' * abrir_obj
                return truncado + cierre
    return None

DOCLING_URL = os.getenv("DOCLING_URL", "http://localhost:5001")
BEDROCK_URL = os.getenv("BEDROCK_URL", "http://localhost:8080")
BEDROCK_API_KEY = os.getenv("BEDROCK_API_KEY")
BEDROCK_MODEL = os.getenv("BEDROCK_MODEL", "us.anthropic.claude-sonnet-4-20250514-v1:0")

client = OpenAI(
    base_url=f"{BEDROCK_URL}/api/v1",
    api_key=BEDROCK_API_KEY
)

def pdf_a_markdown(pdf_path: str) -> str:
    print(f"[Docling] Procesando {pdf_path}...")
    with open(pdf_path, "rb") as f:
        response = requests.post(
            f"{DOCLING_URL}/v1/convert/file",
            files={"files": (pdf_path, f, "application/pdf")},
            data={
                "to_formats": "md",
                "image_export_mode": "placeholder",
                "include_images": "false",
            },
            timeout=600
        )
    if response.status_code != 200:
        raise Exception(f"Docling error {response.status_code}: {response.text}")
    resultado = response.json()
    markdown = resultado["document"]["md_content"]
    print(f"[Docling] OK — {len(markdown)} caracteres extraídos")
    return markdown

def llamar_claude(prompt: str, label: str, max_tokens: int = 4096) -> dict:
    print(f"[Claude] {label}...")
    response = client.chat.completions.create(
        model=BEDROCK_MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}]
    )

    texto = response.choices[0].message.content.strip()
    finish_reason = response.choices[0].finish_reason
    slug = label.replace(' ', '_').replace('/', '-')

    if finish_reason == "length":
        fname = f"/tmp/claude_truncado_{slug}.txt"
        with open(fname, "w") as f:
            f.write(texto)
        raise Exception(
            f"Respuesta truncada en '{label}' con max_tokens={max_tokens}. Ver {fname}"
        )
    
    if texto.startswith("```"):
        lineas = texto.split("\n")
        texto = "\n".join(lineas[1:-1])
    
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        # Intentar reparar JSON truncado cerrando arrays/objetos abiertos
        reparado = _reparar_json(texto)
        if reparado:
            try:
                return json.loads(reparado)
            except json.JSONDecodeError:
                pass
        # Si no se pudo reparar, reintentar la llamada una vez
        print(f"[Claude] JSON inválido en '{label}', reintentando...")
        response = client.chat.completions.create(
            model=BEDROCK_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )
        texto2 = response.choices[0].message.content.strip()
        if texto2.startswith("```"):
            lineas2 = texto2.split("\n")
            texto2 = "\n".join(lineas2[1:-1])
        try:
            return json.loads(texto2)
        except json.JSONDecodeError as e2:
            reparado2 = _reparar_json(texto2)
            if reparado2:
                try:
                    return json.loads(reparado2)
                except json.JSONDecodeError:
                    pass
            fname = f"/tmp/claude_error_{slug}.txt"
            with open(fname, "w") as f:
                f.write(texto2)
            raise Exception(f"JSON inválido en '{label}' (tras retry): {e2}. Ver {fname}")

def extraer_datos(markdown: str) -> dict:
    # Llamada 1: metadatos + notas ME/MT
    r1 = llamar_claude(
        PROMPT_METADATOS_Y_ME.replace("{markdown}", markdown),
        "metadatos y ME-MT",
        max_tokens=32768
    )
    
    # Llamada 2a: distritos I-IV
    r2a = llamar_claude(
        PROMPT_DISTRITOS_1_4.replace("{markdown}", markdown),
        "distritos I-IV",
        max_tokens=32768
    )
    
    # Llamada 2b: distritos V-VII
    r2b = llamar_claude(
        PROMPT_DISTRITOS_5_7.replace("{markdown}", markdown),
        "distritos V-VII",
        max_tokens=32768
    )
    
    # Llamada 3: notas AS y AT
    r3 = llamar_claude(
        PROMPT_AS_AT.replace("{markdown}", markdown),
        "AS y AT",
        max_tokens=32768
    )
    
    # Llamada 4: temas varios
    r4 = llamar_claude(
        PROMPT_TEMAS_VARIOS.replace("{markdown}", markdown),
        "temas varios",
        max_tokens=32768
    )
    
    datos = {
        "acta": r1["acta"],
        "notas_me_mt": r1["notas_me_mt"],
        "notas_distritos": r2a["notas_distritos"] + r2b["notas_distritos"],
        "notas_as": r3["notas_as"],
        "notas_at": r3["notas_at"],
        "temas_varios": r4["temas_varios"]
    }
    
    for seccion in ["notas_me_mt", "notas_distritos", "notas_as", "notas_at"]:
        datos[seccion] = [normalizar_nota(n, markdown) for n in datos[seccion]]
    
    total_notas = sum(
        len(datos[s]) for s in ["notas_me_mt", "notas_distritos", "notas_as", "notas_at"]
    )
    print(f"[Claude] OK — {total_notas} notas extraídas, {len(datos['temas_varios'])} temas varios")
    
    return datos
