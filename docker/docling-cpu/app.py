"""
Docling Serve con extracción mejorada de tablas usando pdfplumber.

Este módulo extiende el comportamiento de docling-serve para:
1. Detectar tablas financieras en PDFs
2. Extraerlas usando pdfplumber (mejor precisión que OCR puro)
3. Integrarlas en el documento Markdown resultante

Mantiene compatibilidad 100% con la API de docling-serve original.
"""

import io
import json
import logging
from typing import List, Dict, Optional, Any
from pathlib import Path
from dataclasses import dataclass

from fastapi import FastAPI, UploadFile, File, HTTPException, status
from fastapi.responses import JSONResponse
from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import InputFormat

# Intentar importar pdfplumber (opcional pero recomendado)
try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False
    logging.warning("pdfplumber no disponible, usando extracción de tablas de docling solamente")

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Crear aplicación FastAPI (compatible con docling-serve)
app = FastAPI(
    title="Docling Serve - Mejorado para Tablas Financieras",
    description="Extensión de docling-serve con pdfplumber para extracción precisa de tablas",
    version="2.0.0"
)

# Inicializar converter de docling
converter = DocumentConverter()


@dataclass
class ExtractedTable:
    """Representa una tabla extraída del PDF."""
    page: int
    index: int
    data: List[List[str]]
    type: str  # 'financiera', 'asistencia', 'general'
    
    def is_financial(self) -> bool:
        """Determina si es una tabla financiera basada en contenido."""
        text = " ".join([str(cell) for row in self.data for cell in row if cell])
        financial_keywords = [
            '$', 'PRESUPUESTO', 'TESORERÍA', 'TESORERIA', 'RECAUDACIÓN', 
            'INGRESO', 'EGRESO', 'TOTAL', 'SALDO', 'CUOTA', 'BALANCE',
            'FINANCIERO', 'ECONÓMICO', 'PARTIDA', 'MATRÍCULA', 'CUOTA'
        ]
        return any(keyword in text.upper() for keyword in financial_keywords)


def extract_tables_with_pdfplumber(pdf_bytes: bytes) -> List[ExtractedTable]:
    """
    Extrae tablas usando pdfplumber (más preciso para tablas financieras).
    
    Args:
        pdf_bytes: Contenido del PDF en bytes
        
    Returns:
        Lista de tablas extraídas
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
                    
                    # Limpiar celdas
                    cleaned = []
                    for row in table:
                        cleaned_row = []
                        for cell in row:
                            if cell:
                                # Limpiar espacios y normalizar
                                text = str(cell).replace('\n', ' ').strip()
                                text = ' '.join(text.split())  # Normalizar espacios
                                cleaned_row.append(text)
                            else:
                                cleaned_row.append("")
                        cleaned.append(cleaned_row)
                    
                    # Crear objeto tabla
                    table_obj = ExtractedTable(
                        page=page_num,
                        index=table_idx,
                        data=cleaned,
                        type='general'
                    )
                    
                    # Clasificar
                    if table_obj.is_financial():
                        table_obj.type = 'financiera'
                    elif any(kw in " ".join([str(c) for c in cleaned[0]]).upper() 
                             for kw in ['ASISTENCIA', 'PRESENTE', 'VOCAL', 'CONSEJERO']):
                        table_obj.type = 'asistencia'
                    
                    tables.append(table_obj)
                    
        logger.info(f"pdfplumber extrajo {len(tables)} tablas")
        
    except Exception as e:
        logger.error(f"Error extrayendo tablas con pdfplumber: {e}")
    
    return tables


def format_table_to_markdown(table_data: List[List[str]]) -> str:
    """
    Formatea una tabla a Markdown con formato profesional.
    
    Args:
        table_data: Lista de filas, cada fila es lista de celdas
        
    Returns:
        String en formato Markdown
    """
    if not table_data or len(table_data) < 1:
        return ""
    
    # Normalizar número de columnas
    max_cols = max(len(row) for row in table_data)
    normalized = []
    for row in table_data:
        while len(row) < max_cols:
            row.append("")
        normalized.append(row[:max_cols])
    
    lines = []
    
    # Header
    header = normalized[0]
    lines.append("| " + " | ".join(header) + " |")
    
    # Separador
    lines.append("| " + " | ".join(["---"] * max_cols) + " |")
    
    # Filas de datos
    for row in normalized[1:]:
        # Escapar caracteres especiales en celdas
        escaped_row = []
        for cell in row:
            # Escapar pipes y asteriscos
            cell = str(cell).replace("|", "\\|").replace("*", "\\*")
            escaped_row.append(cell)
        lines.append("| " + " | ".join(escaped_row) + " |")
    
    return "\n".join(lines)


def enhance_markdown_with_tables(original_markdown: str, tables: List[ExtractedTable]) -> str:
    """
    Mejora el Markdown de docling insertando las tablas extraídas con pdfplumber.
    
    Args:
        original_markdown: Markdown generado por docling
        tables: Tablas extraídas por pdfplumber
        
    Returns:
        Markdown mejorado
    """
    if not tables:
        return original_markdown
    
    sections = []
    
    # Header informativo
    sections.append("<!-- Procesado con Docling + pdfplumber para tablas financieras -->")
    sections.append("")
    
    # Separar tablas financieras del resto
    financial_tables = [t for t in tables if t.type == 'financiera']
    other_tables = [t for t in tables if t.type != 'financiera']
    
    # Si hay tablas financieras, agregar sección especial al inicio
    if financial_tables:
        sections.append("## 📊 Tablas Financieras Extraídas")
        sections.append("")
        sections.append("Las siguientes tablas fueron procesadas con extracción especializada:")
        sections.append("")
        
        for i, table in enumerate(financial_tables, 1):
            sections.append(f"### Tabla Financiera {i} (Página {table.page})")
            sections.append("")
            sections.append(format_table_to_markdown(table.data))
            sections.append("")
    
    # Contenido original de docling
    sections.append("---")
    sections.append("")
    sections.append("## 📝 Contenido Completo del Documento")
    sections.append("")
    sections.append(original_markdown)
    
    # Si hay otras tablas, agregar al final
    if other_tables:
        sections.append("")
        sections.append("## 📋 Otras Tablas Identificadas")
        sections.append("")
        
        for i, table in enumerate(other_tables, 1):
            sections.append(f"### Tabla {i} (Página {table.page})")
            sections.append("")
            sections.append(format_table_to_markdown(table.data))
            sections.append("")
    
    return "\n".join(sections)


@app.get("/health")
def health():
    """Endpoint de health check (compatible con docling-serve)."""
    return {
        "status": "ok",
        "service": "docling-serve-enhanced",
        "pdfplumber_available": PDFPLUMBER_AVAILABLE,
        "features": ["ocr", "table_extraction", "financial_tables"]
    }


@app.get("/")
def root():
    """Endpoint raíz con información del servicio."""
    return {
        "service": "Docling Serve - Mejorado para Tablas Financieras",
        "version": "2.0.0",
        "endpoints": {
            "health": "/health",
            "convert": "/v1/convert/file (POST)"
        },
        "enhancements": [
            "Extracción de tablas con pdfplumber",
            "Detección automática de tablas financieras",
            "Formateo Markdown mejorado",
            "Compatible 100% con API docling-serve"
        ]
    }


@app.post("/v1/convert/file")
def convert(
    file: Optional[UploadFile] = File(None),
    files: Optional[UploadFile] = File(None)
):
    """
    Convierte un PDF a Markdown con extracción mejorada de tablas.
    
    Compatible con el endpoint original de docling-serve,
    pero agrega extracción especializada de tablas financieras.
    
    Args:
        file: Archivo PDF a procesar
        
    Returns:
        JSON con el texto extraído en formato Markdown
    """
    # OpenWebUI usa 'files' (plural), nosotros esperamos 'file' (singular)
    # Aceptamos ambos para compatibilidad
    uploaded_file = file or files
    
    if not uploaded_file:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Field required: file o files"
        )
    
    # Validar tipo de archivo
    if uploaded_file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Se requiere un archivo PDF"
        )
    
    try:
        # Leer contenido
        content = uploaded_file.file.read()
        logger.info(f"Procesando archivo: {uploaded_file.filename} ({len(content)} bytes)")
        
        # Paso 1: Extraer tablas con pdfplumber (mejor para tablas)
        tables = []
        if PDFPLUMBER_AVAILABLE:
            logger.info("Extrayendo tablas con pdfplumber...")
            tables = extract_tables_with_pdfplumber(content)
            logger.info(f"Tablas encontradas: {len(tables)} (financieras: {len([t for t in tables if t.type == 'financiera'])})")
        
        # Paso 2: Procesar con Docling para texto y estructura general
        logger.info("Procesando con Docling...")
        result = converter.convert(io.BytesIO(content))
        original_markdown = result.document.export_to_markdown()
        
        # Paso 3: Combinar resultados si hay tablas
        if tables:
            logger.info("Combinando resultados de Docling + pdfplumber...")
            enhanced_markdown = enhance_markdown_with_tables(original_markdown, tables)
        else:
            enhanced_markdown = original_markdown
        
        logger.info("Procesamiento completado exitosamente")
        
        return JSONResponse({
            "text": enhanced_markdown,
            "metadata": {
                "filename": file.filename,
                "original_size": len(content),
                "tables_extracted": len(tables),
                "financial_tables": len([t for t in tables if t.type == 'financiera']),
                "processor": "docling+pdfplumber"
            }
        })
        
    except Exception as e:
        logger.error(f"Error procesando archivo: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error procesando PDF: {str(e)}"
        )


# Endpoint legacy para compatibilidad
@app.post("/convert")
def convert_legacy(file: UploadFile = File(...)):
    """Alias legacy del endpoint de conversión."""
    return convert(file)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5001)
