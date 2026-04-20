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
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from extractor import pdf_a_markdown, extraer_datos
from db import guardar_todo
from qdrant_index import indexar_acta

LOG_PATH = Path(__file__).resolve().parent.parent.parent / "ingesta-log.md"


def _log(line: str):
    """Agrega una línea al log markdown de ingesta."""
    if not LOG_PATH.exists():
        LOG_PATH.write_text(
            "# Log de ingesta de actas\n\n"
            "| Fecha | Archivo | Acta N° | DB id | Notas | Chunks | Tiempo | Estado |\n"
            "|-------|---------|---------|-------|-------|--------|--------|--------|\n",
            encoding="utf-8",
        )
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


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
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M")

    try:
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

        # Detectar tipo desde el nombre del archivo (ACTA_CS_... / ACTA_ME_...)
        name_upper = path.name.upper()
        if "_CS_" in name_upper:
            datos["acta"]["tipo"] = "Consejo Superior"
        elif "_ME_" in name_upper:
            datos["acta"]["tipo"] = "Mesa Ejecutiva"

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
        acta_num = datos['acta']['acta_numero']
        total_notas = sum(
            len(datos[s]) for s in ["notas_me_mt", "notas_distritos", "notas_as", "notas_at"]
        )

        print(f"\n{'='*60}")
        print(f"✓ Ingesta completada en {elapsed:.1f}s")
        print(f"  Acta N° {acta_num} → PostgreSQL id {acta_id}")
        print(f"{'='*60}\n")

        _log(f"| {ahora} | {path.name} | {acta_num} | {acta_id} | {total_notas} | — | {elapsed:.0f}s | OK |")

    except Exception as e:
        elapsed = time.time() - inicio
        print(f"\nERROR en {path.name}: {e}")
        _log(f"| {ahora} | {path.name} | — | — | — | — | {elapsed:.0f}s | ERROR: {e} |")
        raise


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python ingest.py <path_al_pdf>")
        sys.exit(1)

    ingestar(sys.argv[1])
