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
            f"{DOCLING_URL}/v1alpha/convert/file",
            files={"files": (pdf_path, f, "application/pdf")},
            data={"to_formats": "md"},
            timeout=120
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
    
    if finish_reason == "length":
        fname = f"/tmp/claude_truncado_{label.replace(' ','_')}.txt"
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
    except json.JSONDecodeError as e:
        fname = f"/tmp/claude_error_{label.replace(' ','_')}.txt"
        with open(fname, "w") as f:
            f.write(texto)
        raise Exception(f"JSON inválido en '{label}': {e}. Ver {fname}")

def extraer_datos(markdown: str) -> dict:
    # Llamada 1: metadatos + notas ME/MT
    r1 = llamar_claude(
        PROMPT_METADATOS_Y_ME.replace("{markdown}", markdown),
        "metadatos y ME/MT",
        max_tokens=4096
    )
    
    # Llamada 2a: distritos I-IV
    r2a = llamar_claude(
        PROMPT_DISTRITOS_1_4.replace("{markdown}", markdown),
        "distritos I-IV",
        max_tokens=6144
    )
    
    # Llamada 2b: distritos V-VII
    r2b = llamar_claude(
        PROMPT_DISTRITOS_5_7.replace("{markdown}", markdown),
        "distritos V-VII",
        max_tokens=4096
    )
    
    # Llamada 3: notas AS y AT
    r3 = llamar_claude(
        PROMPT_AS_AT.replace("{markdown}", markdown),
        "AS y AT",
        max_tokens=6144
    )
    
    # Llamada 4: temas varios
    r4 = llamar_claude(
        PROMPT_TEMAS_VARIOS.replace("{markdown}", markdown),
        "temas varios",
        max_tokens=2048
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
