# Pipeline de ingesta de actas — Colegio de Técnicos PBA

Toma un acta PDF del Colegio de Técnicos, la procesa con Docling (OCR GPU), extrae datos estructurados con Claude via Bedrock, y los inserta en PostgreSQL + Qdrant.

## Arquitectura

```
PDF
 │
 ▼
Docling GPU (OCR → Markdown estructurado)
 │
 ▼
Claude Sonnet via Bedrock Gateway (5 llamadas por acta, extrae JSON)
 │
 ▼
normalizer.py (corrige errores OCR: matrículas truncadas, códigos corruptos)
 │
 ├──► PostgreSQL colegio_tecnicos  (datos estructurados, consultables)
 └──► Qdrant actas_colegio         (chunks semánticos para RAG)
```

## Requisitos previos

- Python 3.11+
- Acceso al cluster (`kubectl` configurado apuntando a `colegio-staging`)
- Nodo GPU activo (para Docling) — ver [GPU-BURST.md](../../GPU-BURST.md)
- Port-forwards activos (ver Setup)

## Setup

```bash
cd scripts/ingest
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Crear `.env` (o exportar las variables):

```bash
DOCLING_URL=http://localhost:5001
BEDROCK_URL=http://localhost:8080
BEDROCK_API_KEY=bedrock-gateway-internal-key-2026
BEDROCK_MODEL=global.anthropic.claude-sonnet-4-6
EMBEDDING_MODEL=amazon.titan-embed-text-v2:0
DATABASE_URL=postgresql://ragsystemuser:admin123@localhost:5432/colegio_tecnicos
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=actas_colegio
```

Port-forwards necesarios:

```bash
kubectl port-forward -n rag-system svc/docling        5001:5001 &
kubectl port-forward -n rag-system svc/bedrock-gateway 8080:80  &
kubectl port-forward -n rag-system svc/postgres        5432:5432 &
kubectl port-forward -n rag-system svc/qdrant-service  6333:6333 &
```

## Uso

```bash
source venv/bin/activate

# Ingestar un acta
python3 ingest.py /ruta/al/ACTA_ME_924_2024.pdf

# El script detecta el tipo (ME/CS) desde el nombre del archivo
# y registra el resultado en ../../ingesta-log.md
```

El script es **idempotente**: si el acta ya existe en la DB, actualiza en vez de duplicar.

## Archivos

| Archivo | Descripción |
|---|---|
| `ingest.py` | Entry point — recibe el PDF, orquesta todo el pipeline |
| `extractor.py` | Llama a Docling y luego a Claude (5 llamadas) para extraer JSON |
| `prompts.py` | Los 5 prompts de extracción (metadatos+ME, distritos 1-4, distritos 5-7, AS/AT, temas varios) |
| `normalizer.py` | Corrige errores OCR: completa matrículas truncadas, normaliza códigos corruptos |
| `db.py` | Inserta/actualiza en PostgreSQL (`colegio_tecnicos`) |
| `qdrant_index.py` | Genera embeddings con Titan v2 e indexa chunks en Qdrant |
| `test_sin_docling.py` | Test que saltea Docling, usa un `.md` pre-generado en `/tmp/` |
| `requirements.txt` | Dependencias Python |

## Estrategia de extracción (5 llamadas a Claude por acta)

| Llamada | Sección del acta | max_tokens |
|---|---|---|
| 1 | Metadatos del acta + Notas ME y MT | 32768 |
| 2a | Notas Distrito I, II, III y IV | 32768 |
| 2b | Notas Distrito V, VI y VII | 32768 |
| 3 | Notas AS y AT | 32768 |
| 4 | Temas varios | 32768 |

Costo estimado por acta: ~$0.08. Carga histórica de 500 actas: ~$40.

## Schema PostgreSQL (`colegio_tecnicos`)

```sql
actas                   -- numero, tipo, fecha, participantes[], pdf_url
notas_ingresadas        -- acta_id, seccion, codigo_nota, tema, descripcion, resolucion
personas_mencionadas    -- nota_id, nombre_completo, numero_matricula, rol_mencion
expedientes_mencionados -- nota_id, numero_expediente, referencia_ctd
resoluciones_distritales-- nota_id, numero_resolucion, tecnico, matricula, tipo, distrito
temas_varios            -- acta_id, numero_punto, descripcion, resolucion
```

## Actualizar pdf_url tras subir PDFs nuevos a OpenWebUI Knowledge

Cuando se suben nuevos PDFs a la Knowledge Base `be60e885-d097-486c-8d5e-7f6b3049244d`:

```bash
source venv/bin/activate
python3 ../populate_pdf_urls.py
```

El script lee la tabla `file` de `ragsystemdb` (OpenWebUI), extrae el `acta_numero` del nombre del archivo (`ACTA_ME_924_2024.pdf`), y actualiza `actas.pdf_url` con la URL directa al PDF.

## Log de ingesta

Cada ejecución registra una fila en `../../ingesta-log.md`:

```
| fecha | archivo | acta_numero | db_id | notas | tiempo | estado |
```

## Notas técnicas

- Docling corre con EasyOCR en GPU, soporte español nativo (`spa,eng`)
- Endpoint Docling: `POST /v1/convert/file` con `image_export_mode=placeholder` (evita markdown inflado con imágenes)
- Timeout Docling: 600s (actas grandes pueden tardar)
- El normalizer completa matrículas truncadas por OCR propagando el contexto del markdown completo
- La base `ragsystemdb` es de OpenWebUI — no agregar tablas ahí
