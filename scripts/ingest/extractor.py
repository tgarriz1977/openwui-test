import requests
import json
from openai import OpenAI
from prompts import PROMPT_METADATOS_Y_ME, PROMPT_DISTRITOS_Y_RESTO
from normalizer import normalizar_nota
import os
from dotenv import load_dotenv

load_dotenv()

DOCLING_URL = os.getenv("DOCLING_URL", "http://localhost:5001")
BEDROCK_URL = os.getenv("BEDROCK_URL", "http://localhost:8080")
BEDROCK_API_KEY = os.getenv("BEDROCK_API_KEY")
BEDROCK_MODEL = os.getenv("BEDROCK_MODEL", "anthropic.claude-sonnet-4-20250514-v1:0")

client = OpenAI(
    base_url=f"{BEDROCK_URL}/api/v1",
    api_key=BEDROCK_API_KEY
)

def pdf_a_markdown(pdf_path: str) -> str:
    """Envía el PDF a Docling y recibe el Markdown estructurado"""
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
    # Docling devuelve una lista de documentos convertidos
    markdown = resultado["document"]["md_content"]
    print(f"[Docling] OK — {len(markdown)} caracteres extraídos")
    return markdown

def llamar_claude(prompt: str) -> dict:
    """Llama a Claude via bedrock-gateway y parsea el JSON de respuesta"""
    response = client.chat.completions.create(
        model=BEDROCK_MODEL,
        max_tokens=4096,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    
    texto = response.choices[0].message.content.strip()
    
    # Limpia bloques de código si Claude los incluye de todas formas
    if texto.startswith("```"):
        lineas = texto.split("\n")
        texto = "\n".join(lineas[1:-1])
    
    return json.loads(texto)

def extraer_datos(markdown: str) -> dict:
    """Ejecuta los dos prompts en serie y combina los resultados"""
    print("[Claude] Extrayendo metadatos y notas ME/MT...")
    prompt1 = PROMPT_METADATOS_Y_ME.replace("{markdown}", markdown)
    resultado1 = llamar_claude(prompt1)
    
    print("[Claude] Extrayendo distritos, AS, AT y temas varios...")
    prompt2 = PROMPT_DISTRITOS_Y_RESTO.replace("{markdown}", markdown)
    resultado2 = llamar_claude(prompt2)
    
    # Combina ambos resultados
    datos = {
        "acta": resultado1["acta"],
        "notas_me_mt": resultado1["notas_me_mt"],
        "notas_distritos": resultado2["notas_distritos"],
        "notas_as": resultado2["notas_as"],
        "notas_at": resultado2["notas_at"],
        "temas_varios": resultado2["temas_varios"]
    }
    
    # Normaliza códigos OCR en todas las notas
    for seccion in ["notas_me_mt", "notas_distritos", "notas_as", "notas_at"]:
        datos[seccion] = [normalizar_nota(n) for n in datos[seccion]]
    
    total_notas = sum(len(datos[s]) for s in ["notas_me_mt", "notas_distritos", "notas_as", "notas_at"])
    print(f"[Claude] OK — {total_notas} notas extraídas, {len(datos['temas_varios'])} temas varios")
    
    return datos
