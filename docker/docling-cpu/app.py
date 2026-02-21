"""
Docling Serve con extracción mejorada de tablas usando pdfplumber como respaldo.

Este módulo extiende docling-serve para:
1. Usar Docling nativo para texto y tablas (export_to_markdown incluye tablas)
2. Usar pdfplumber solo para tablas financieras complejas que Docling no detecte bien
3. Combinar ambos resultados inteligentemente

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
from docling.datamodel.base_models import InputFormat, DocumentStream

# Intentar importar pdfplumber (opcional pero recomendado)
try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False
    logging.warning("pdfplumber no disponible")

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Crear aplicación FastAPI (compatible con docling-serve)
app = FastAPI(
    title="Docling Serve - Mejorado para Tablas Financieras",
    description="Extensión de docling-serve con pdfplumber para tablas complejas",
    version="2.1.0"
)

# Inicializar converter de docling
converter = DocumentConverter()


def extract_tables_with_pdfplumber(pdf_bytes: bytes) -> List[Dict]:
    """
    Extrae tablas usando pdfplumber como respaldo.
    Solo usado si Docling no detecta tablas financieras.
    """
    tables = []
    
    if not PDFPLUMBER_AVAILABLE:
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
                        cleaned_row = [str(cell).replace('\n', ' ').strip() if cell else "" for cell in row]
                        cleaned.append(cleaned_row)
                    
                    tables.append({
                        'page': page_num,
                        'index': table_idx,
                        'data': cleaned,
                        'rows': len(cleaned)
                    })
                    
        logger.info(f"pdfplumber extrajo {len(tables)} tablas")
        
    except Exception as e:
        logger.warning(f"Error con pdfplumber: {e}")
    
    return tables


def format_table_to_markdown(table_data: List[List[str]]) -> str:
    """Formatea una tabla a Markdown."""
    if not table_data or len(table_data) < 1:
        return ""
    
    max_cols = max(len(row) for row in table_data)
    normalized = []
    for row in table_data:
        while len(row) < max_cols:
            row.append("")
        normalized.append(row[:max_cols])
    
    lines = []
    header = normalized[0]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join(["---"] * max_cols) + " |")
    
    for row in normalized[1:]:
        escaped_row = [str(cell).replace("|", "\\|") for cell in row]
        lines.append("| " + " | ".join(escaped_row) + " |")
    
    return "\n".join(lines)


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
        "version": "2.1.0",
        "endpoints": {
            "health": "/health",
            "convert": "/v1/convert/file (POST)"
        }
    }


@app.post("/v1/convert/file")
def convert(
    file: Optional[UploadFile] = File(None),
    files: Optional[UploadFile] = File(None)
):
    """
    Convierte un PDF a Markdown con extracción de tablas.
    
    Estrategia:
    1. Usar Docling nativo (ya incluye tablas en el Markdown)
    2. Si no hay tablas detectadas, usar pdfplumber como respaldo
    """
    # Aceptar file o files (OpenWebUI usa 'files')
    uploaded_file = file or files
    
    if not uploaded_file:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Field required: file o files"
        )
    
    try:
        # Leer contenido del PDF
        content = uploaded_file.file.read()
        logger.info(f"Procesando: {uploaded_file.filename} ({len(content)} bytes)")
        
        # Paso 1: Procesar con Docling nativo
        # Docling ya extrae texto Y tablas en el Markdown
        logger.info("Procesando con Docling nativo...")
        doc_stream = DocumentStream(name=uploaded_file.filename, stream=io.BytesIO(content))
        result = converter.convert(doc_stream)
        
        # Obtener Markdown con tablas (Docling ya incluye las tablas)
        markdown = result.document.export_to_markdown()
        
        # Contar tablas detectadas por Docling
        docling_tables = list(result.document.tables) if hasattr(result.document, 'tables') else []
        logger.info(f"Docling detectó {len(docling_tables)} tablas")
        
        # Verificar si hay tablas financieras en el contenido
        has_financial_content = any(keyword in markdown.upper() for keyword in [
            'PRESUPUESTO', 'TESORERIA', 'TESORERÍA', 'RECAUDACION', 
            'INGRESO', 'EGRESO', 'TOTAL', 'BALANCE'
        ])
        
        # Si hay contenido financiero pero pocas tablas, enriquecer con pdfplumber
        pdfplumber_tables = []
        if PDFPLUMBER_AVAILABLE and has_financial_content and len(docling_tables) < 3:
            logger.info("Buscando tablas adicionales con pdfplumber...")
            pdfplumber_tables = extract_tables_with_pdfplumber(content)
            logger.info(f"pdfplumber encontró {len(pdfplumber_tables)} tablas adicionales")
        
        # Si pdfplumber encontró tablas que Docling no detectó, agregarlas
        if pdfplumber_tables and len(pdfplumber_tables) > len(docling_tables):
            logger.info("Agregando tablas de pdfplumber al documento...")
            
            # Agregar sección de tablas adicionales al final
            markdown += "\n\n## 📊 Tablas Adicionales Extraídas\n\n"
            markdown += "*Las siguientes tablas fueron procesadas con extracción especializada:*\n\n"
            
            for i, table in enumerate(pdfplumber_tables, 1):
                markdown += f"### Tabla {i} (Página {table['page']})\n\n"
                markdown += format_table_to_markdown(table['data'])
                markdown += "\n\n"
        
        logger.info("Procesamiento completado exitosamente")
        
        return JSONResponse({
            "text": markdown,
            "metadata": {
                "filename": uploaded_file.filename,
                "original_size": len(content),
                "docling_tables": len(docling_tables),
                "pdfplumber_tables": len(pdfplumber_tables),
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
