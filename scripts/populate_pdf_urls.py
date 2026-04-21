"""
Lee los archivos de la tabla `file` de ragsystemdb (OpenWebUI),
extrae el acta_numero del filename y actualiza actas.pdf_url en colegio_tecnicos.

Uso:
    python3 populate_pdf_urls.py
"""

import os
import re
import sys

import psycopg2

PUBLIC_URL = os.getenv("OPENWEBUI_PUBLIC_URL", "https://asistente.tecnicos.org.ar")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://ragsystemuser:admin123@localhost:5432/colegio_tecnicos")
OWUI_DATABASE_URL = os.getenv("OWUI_DATABASE_URL", "postgresql://ragsystemuser:admin123@localhost:5432/ragsystemdb")

KNOWLEDGE_ID = "be60e885-d097-486c-8d5e-7f6b3049244d"
FILENAME_RE = re.compile(r"ACTA_(?:ME|CS)_(\d+)_\d+\.pdf", re.IGNORECASE)


def fetch_file_mapping() -> dict[int, str]:
    """Devuelve {acta_numero: url} tomando el primer file_id por número de acta."""
    conn = psycopg2.connect(OWUI_DATABASE_URL)
    mapping: dict[int, str] = {}
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, filename FROM file WHERE meta::text LIKE %s ORDER BY id",
                (f"%{KNOWLEDGE_ID}%",),
            )
            for file_id, filename in cur.fetchall():
                m = FILENAME_RE.search(filename)
                if m:
                    numero = int(m.group(1))
                    if numero not in mapping:  # primer id gana
                        mapping[numero] = f"{PUBLIC_URL}/api/v1/files/{file_id}/content"
    finally:
        conn.close()
    return mapping


def main():
    print("Leyendo archivos de ragsystemdb...")
    mapping = fetch_file_mapping()
    print(f"  {len(mapping)} actas con PDF en OpenWebUI")

    if not mapping:
        print("ERROR: no se encontraron archivos ACTA*")
        sys.exit(1)

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            updated, missing = 0, []
            for numero, url in mapping.items():
                cur.execute("UPDATE actas SET pdf_url = %s WHERE acta_numero = %s", (url, numero))
                if cur.rowcount:
                    updated += 1
                else:
                    missing.append(numero)
        conn.commit()
        print(f"  {updated} actas actualizadas en colegio_tecnicos")
        if missing:
            print(f"  En OpenWebUI pero no en DB: {sorted(missing)}")

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM actas WHERE pdf_url IS NOT NULL")
            print(f"  actas con pdf_url: {cur.fetchone()[0]}")
            cur.execute("SELECT COUNT(*) FROM actas WHERE pdf_url IS NULL")
            print(f"  actas sin pdf_url:  {cur.fetchone()[0]}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
