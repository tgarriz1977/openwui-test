#!/usr/bin/env python3
"""
Script de ingesta de actas del Colegio de Técnicos de la Provincia de Buenos Aires.

Uso:
    python ingest.py <path_al_pdf>
    python ingest.py /home/admin/actas/ACTA_875_FIRMADA.pdf

El script:
1. Envía el PDF a Docling para extracción de Markdown estructurado
2. Llama a Claude (via Bedrock) con dos prompts en serie para extraer JSON
3. Normaliza códigos mal reconocidos por OCR
4. Inserta los datos estructurados en PostgreSQL
5. Indexa los chunks en Qdrant para búsqueda semántica
"""

import sys
import os
import json
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from extractor import pdf_a_markdown, extraer_datos
from db import guardar_todo
from qdrant_index import indexar_acta

def ingestar(pdf_path: str):
    path = Path(pdf_path)
    if not path.exists():
        print(f"ERROR: No se encuentra el archivo {pdf_path}")
        sys.exit(1)
    
    if not path.suffix.lower() == ".pdf":
        print(f"ERROR: El archivo debe ser un PDF")
        sys.exit(1)
    
    print(f"\n{'='*60}")
    print(f"Ingesta: {path.name}")
    print(f"{'='*60}\n")
    
    inicio = time.time()
    
    # Paso 1: Docling
    print("PASO 1/4 — Extracción Markdown con Docling")
    markdown = pdf_a_markdown(str(path))
    
    # Guarda el markdown para debugging
    markdown_path = path.with_suffix(".md")
    markdown_path.write_text(markdown, encoding="utf-8")
    print(f"[Debug] Markdown guardado en {markdown_path}")
    
    # Paso 2: Claude extrae JSON
    print("\nPASO 2/4 — Extracción estructurada con Claude")
    datos = extraer_datos(markdown)
    
    # Guarda el JSON para debugging
    json_path = path.with_suffix(".json")
    json_path.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[Debug] JSON guardado en {json_path}")
    
    # Paso 3: PostgreSQL
    print("\nPASO 3/4 — Inserción en PostgreSQL")
    acta_id = guardar_todo(datos)
    
    # Paso 4: Qdrant
    print("\nPASO 4/4 — Indexación en Qdrant")
    indexar_acta(markdown, datos, acta_id)
    
    elapsed = time.time() - inicio
    print(f"\n{'='*60}")
    print(f"✓ Ingesta completada en {elapsed:.1f}s")
    print(f"  Acta N° {datos['acta']['acta_numero']} → PostgreSQL id {acta_id}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python ingest.py <path_al_pdf>")
        sys.exit(1)
    
    ingestar(sys.argv[1])
