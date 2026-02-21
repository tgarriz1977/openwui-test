"""
Docling Serve con extracción especializada de tablas usando pdfplumber.

Estrategia:
1. Docling para texto y estructura general
2. pdfplumber EXCLUSIVAMENTE para tablas financieras (mejor precisión)
3. Reemplazar tablas malformadas de Docling con tablas limpias de pdfplumber

Mantiene compatibilidad 100% con la API de docling-serve original.
"""

import io
import re
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass

from fastapi import FastAPI, UploadFile, File, HTTPException, status
from fastapi.responses import JSONResponse
from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import DocumentStream

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
    version="2.2.0"
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
        'MATRICULA', 'MATRÍCULA', 'GASTOS', 'SUELDOS', 'VIATICOS'
    ]
    
    return any(keyword in text for keyword in financial_keywords)


def clean_cell(cell) -> str:
    """Limpia el contenido de una celda."""
    if cell is None:
        return ""
    text = str(cell).replace('\n', ' ').strip()
    text = ' '.join(text.split())  # Normalizar espacios
    return text


def extract_all_tables_with_pdfplumber(pdf_bytes: bytes) -> List[FinancialTable]:
    """
    Extrae TODAS las tablas usando pdfplumber (no solo financieras).
    """
    tables = []
    
    if not PDFPLUMBER_AVAILABLE:
        logger.warning("pdfplumber no disponible")
        return tables
    
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                page_tables = page.extract_tables()
                
                for table_idx, table in enumerate(page_tables):
                    if not table or len(table) < 2:
                        continue
                    
                    # Limpiar datos
                    cleaned = []
                    for row in table:
                        cleaned_row = [clean_cell(cell) for cell in row]
                        # Ignorar filas vacías
                        if any(cleaned_row):
                            cleaned.append(cleaned_row)
                    
                    if not cleaned or len(cleaned) < 2:
                        continue
                    
                    # Detectar si es tabla financiera para el título
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
    
    # Calcular número máximo de columnas
    max_cols = max(len(table.headers), max([len(row) for row in table.rows]) if table.rows else 0)
    
    # Normalizar headers
    headers = table.headers + [""] * (max_cols - len(table.headers))
    headers = headers[:max_cols]
    
    # Header Markdown
    lines.append("| " + " | ".join(headers) + " |")
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


def process_document(pdf_bytes: bytes, filename: str) -> str:
    """
    Procesa el documento:
    1. Extrae SOLO TEXTO con Docling (ignora sus tablas malformadas)
    2. Extrae tablas financieras con pdfplumber (mejor calidad)
    3. Combina resultado limpio
    """
    # Paso 1: Docling para TEXTO SOLAMENTE
    logger.info("Extrayendo texto con Docling...")
    doc_stream = DocumentStream(name=filename, stream=io.BytesIO(pdf_bytes))
    result = converter.convert(doc_stream)
    
    # Obtener SOLO TEXTO (export_to_text() no incluye tablas)
    base_text = result.document.export_to_text()
    
    # Paso 2: pdfplumber para TODAS las tablas (no solo financieras)
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


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "docling-serve-enhanced",
        "pdfplumber_available": PDFPLUMBER_AVAILABLE,
        "table_extraction": "pdfplumber-primary"
    }


@app.get("/")
def root():
    return {
        "service": "Docling Serve - Tablas Financieras Optimizadas",
        "version": "2.2.0",
        "features": ["docling-text", "pdfplumber-tables", "financial-extraction"]
    }


@app.post("/v1/convert/file")
def convert(
    file: Optional[UploadFile] = File(None),
    files: Optional[UploadFile] = File(None)
):
    """Convierte PDF a Markdown con tablas financieras optimizadas."""
    uploaded_file = file or files
    
    if not uploaded_file:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Field required: file o files"
        )
    
    try:
        content = uploaded_file.file.read()
        logger.info(f"Procesando: {uploaded_file.filename} ({len(content)} bytes)")
        
        # Procesar documento
        markdown = process_document(content, uploaded_file.filename)
        
        # Contar tablas encontradas
        table_count = markdown.count("### Tabla")
        logger.info(f"Procesamiento completado. Tablas extraídas: {table_count}")
        
        return JSONResponse({
            "document": {
                "md_content": markdown,
                "filename": uploaded_file.filename
            },
            "metadata": {
                "filename": uploaded_file.filename,
                "original_size": len(content),
                "tables_extracted": table_count,
                "processor": "docling-text+pdfplumber-tables"
            }
        })
        
    except Exception as e:
        logger.error(f"Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error: {str(e)}"
        )


@app.post("/convert")
def convert_legacy(file: UploadFile = File(...)):
    return convert(file)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5001)
