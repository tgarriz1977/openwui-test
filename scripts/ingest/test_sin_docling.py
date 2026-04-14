"""
Test de ingesta usando el Markdown del Acta 875 ya extraído por Docling.
Saltea el paso de Docling y va directo a Claude → PostgreSQL → Qdrant.
"""
from pathlib import Path
from extractor import extraer_datos
from db import guardar_todo
from qdrant_index import indexar_acta
import json

# Lee el markdown desde archivo
markdown_path = Path("/tmp/acta_875.md")

if not markdown_path.exists():
    print("ERROR: Creá el archivo /tmp/acta_875.md con el contenido del Markdown de Docling")
    print("Podés copiarlo desde la conversación con Claude")
    exit(1)

markdown = markdown_path.read_text(encoding="utf-8")
print(f"Markdown cargado — {len(markdown)} caracteres")

print("\nPASO 1 — Extracción con Claude...")
datos = extraer_datos(markdown)

print("\nPASO 2 — Guardando JSON de debug...")
Path("/tmp/acta_875_extraido.json").write_text(
    json.dumps(datos, indent=2, ensure_ascii=False), 
    encoding="utf-8"
)

print("\nPASO 3 — Insertando en PostgreSQL...")
acta_id = guardar_todo(datos)

print("\nPASO 4 — Indexando en Qdrant...")
indexar_acta(markdown, datos, acta_id)

print("\n✓ Test completado")
