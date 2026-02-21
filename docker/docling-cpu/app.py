"""
Docling Serve con extracción especializada de tablas usando pdfplumber.

Estrategia v12:
1. Docling SOLO para TEXTO (iterando elementos y excluyendo tablas explícitamente)
2. pdfplumber EXCLUSIVAMENTE para tablas (mejor precisión)
3. Combinar resultado limpio sin duplicación

Mantiene compatibilidad 100% con la API de docling-serve original.
"""

import io
import re
import logging
from typing import List, Optional
from dataclasses import dataclass

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import DocumentStream

# Importar tipos de elementos para filtrado
from docling_core.types.doc import (
    TextItem, SectionHeaderItem, ListItem, 
    TableItem, PictureItem
)

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False
    logging.warning("pdfplumber no disponible")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Docling Serve - Tablas Financieras Optimizadas",
    version="2.3.0"
)

converter = DocumentConverter()


@dataclass
class FinancialTable:
    """Tabla financiera extraída."""
    page: int
    title: str
    headers: List[str]
    rows: List[List[str]]


def is_financial_table(table_data: List[List[str]]) -> bool:
    """Detecta si una tabla contiene datos financieros."""
    if not table_data:
        return False
    
    text = " ".join([str(cell) for row in table_data for cell in row if cell]).upper()
    
    financial_keywords = [
        '$', 'PESOS', 'PRESUPUESTO', 'TESORERIA', 'TESORERÍA', 
        'RECAUDACION', 'INGRESO', 'EGRESO', 'TOTAL', 'SALDO',
        'CUOTA', 'BALANCE', 'FINANCIERO', 'ECONOMICO', 'PARTIDA',
        'FACTURA', 'COBRO', 'PAGO', 'MULTA', 'INTERES', 'MORA'
    ]
    
    return any(kw in text for kw in financial_keywords)


def clean_cell(cell) -> str:
    """Limpia el contenido de una celda."""
    if cell is None:
        return ""
    text = str(cell).strip()
    # Normalizar espacios
    text = re.sub(r'\s+', ' ', text)
    return text


def extract_all_tables_with_pdfplumber(pdf_bytes: bytes) -> List[FinancialTable]:
    """Extrae TODAS las tablas del PDF con pdfplumber (no solo financieras)."""
    tables = []
    
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                page_tables = page.extract_tables()
                
                if not page_tables:
                    continue
                
                for table_idx, table in enumerate(page_tables):
                    if not table or len(table) < 2:
                        continue
                    
                    # Limpiar datos
                    cleaned = []
                    for row in table:
                        cleaned_row = [clean_cell(cell) for cell in row]
                        if any(cleaned_row):
                            cleaned.append(cleaned_row)
                    
                    if not cleaned or len(cleaned) < 2:
                        continue
                    
                    # Detectar tipo para el título
                    is_financial = is_financial_table(cleaned)
                    table_type = "Financiera" if is_financial else "General"
                    title = f"Tabla {table_type} (Página {page_num})"
                    
                    headers = cleaned[0] if cleaned else []
                    rows = cleaned[1:] if len(cleaned) > 1 else []
                    
                    tables.append(FinancialTable(
                        page=page_num,
                        title=title,
                        headers=headers,
                        rows=rows
                    ))
                    logger.info(f"Tabla {table_type} encontrada página {page_num}: {len(rows)} filas")
        
    except Exception as e:
        logger.error(f"Error con pdfplumber: {e}")
    
    return tables


def format_table_to_markdown(table: FinancialTable, table_number: int = None) -> str:
    """Formatea una tabla a Markdown profesional."""
    if not table.rows:
        return ""
    
    lines = []
    
    # Título de la tabla
    if table_number:
        lines.append(f"### Tabla {table_number}: {table.title}")
    else:
        lines.append(f"### {table.title}")
    lines.append("")
    
    # Headers
    headers = table.headers if table.headers else [f"Col {i+1}" for i in range(len(table.rows[0]))]
    
    # Normalizar número de columnas
    max_cols = max(len(headers), max(len(row) for row in table.rows) if table.rows else len(headers))
    
    # Asegurar headers tengan el tamaño correcto
    headers = headers + [""] * (max_cols - len(headers))
    headers = headers[:max_cols]
    
    # Escapar pipes en headers
    escaped_headers = [str(h).replace("|", "\\|") for h in headers]
    lines.append("| " + " | ".join(escaped_headers) + " |")
    lines.append("| " + " | ".join(["---"] * max_cols) + " |")
    
    # Filas
    for row in table.rows:
        # Normalizar número de columnas
        normalized_row = row + [""] * (max_cols - len(row))
        normalized_row = normalized_row[:max_cols]
        
        # Escapar pipes
        escaped = [str(cell).replace("|", "\\|") for cell in normalized_row]
        lines.append("| " + " | ".join(escaped) + " |")
    
    lines.append("")
    return "\n".join(lines)


def extract_text_only_from_docling(doc) -> str:
    """
    Extrae SOLO texto del documento Docling, excluyendo explícitamente tablas.
    Itera sobre los elementos y solo incluye TextItem, SectionHeaderItem, ListItem.
    """
    text_parts = []
    
    for item, level in doc.iterate_items():
        # SOLO incluir elementos de texto, EXCLUIR tablas y pictures
        if isinstance(item, (TextItem, SectionHeaderItem, ListItem)):
            if hasattr(item, 'text') and item.text:
                text_parts.append(item.text)
        # TableItem y PictureItem son explícitamente ignorados
    
    return "\n\n".join(text_parts)


def process_document(pdf_bytes: bytes, filename: str) -> str:
    """
    Procesa el documento:
    1. Extrae SOLO TEXTO con Docling (excluyendo tablas explícitamente)
    2. Extrae tablas con pdfplumber
    3. Combina resultado limpio
    """
    # Paso 1: Docling para TEXTO SOLAMENTE (sin tablas)
    logger.info("Extrayendo texto con Docling (excluyendo tablas)...")
    doc_stream = DocumentStream(name=filename, stream=io.BytesIO(pdf_bytes))
    result = converter.convert(doc_stream)
    
    # Obtener SOLO TEXTO (filtrando explícitamente tablas)
    base_text = extract_text_only_from_docling(result.document)
    
    # Paso 2: pdfplumber para TODAS las tablas
    logger.info("Extrayendo tablas con pdfplumber...")
    all_tables = extract_all_tables_with_pdfplumber(pdf_bytes)
    
    # Paso 3: Construir documento final
    sections = []
    
    # Header
    sections.append(f"# {filename.replace('.pdf', '')}")
    sections.append("")
    sections.append(base_text)
    
    # Agregar tablas bien formateadas al final
    if all_tables:
        sections.append("")
        sections.append("---")
        sections.append("")
        sections.append("## 📊 Tablas Extraídas del Documento")
        sections.append("")
        
        for i, table in enumerate(all_tables, 1):
            sections.append(format_table_to_markdown(table, i))
    
    return "\n".join(sections)


@app.post("/v1/convert/file")
async def convert_file(
    file: Optional[UploadFile] = File(None),
    files: Optional[UploadFile] = File(None)
):
    """
    Endpoint compatible con OpenWebUI y docling-serve.
    Acepta 'file' o 'files' (para compatibilidad).
    """
    uploaded = file or files
    
    if not uploaded:
        return JSONResponse(
            status_code=422,
            content={"error": "No se proporcionó archivo", "detail": "Use 'file' o 'files'"}
        )
    
    try:
        content = await uploaded.read()
        filename = uploaded.filename or "documento.pdf"
        
        logger.info(f"Procesando: {filename} ({len(content)} bytes)")
        
        result = process_document(content, filename)
        
        return JSONResponse({
            "document": {
                "md_content": result,
                "filename": filename
            }
        })
        
    except Exception as e:
        logger.error(f"Error procesando archivo: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "Error procesando archivo", "detail": str(e)}
        )


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "pdfplumber": PDFPLUMBER_AVAILABLE}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5001)
