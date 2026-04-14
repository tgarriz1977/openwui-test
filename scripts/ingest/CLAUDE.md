# Estado del proyecto — Pipeline de ingesta de actas
## Colegio de Técnicos de la Provincia de Buenos Aires

---

## ¿Qué es esto?

Pipeline de ingesta de actas PDF del Colegio de Técnicos. Toma un acta en PDF, la procesa con Docling, extrae datos estructurados con Claude (via Bedrock), los inserta en PostgreSQL y los indexa en Qdrant para búsqueda semántica.

---

## Arquitectura general

```
PDF nuevo
    ↓
Docling (extrae Markdown estructurado)
    ↓
Claude via Bedrock (5 llamadas en serie, extrae JSON)
    ↓
normalizer.py (corrige errores OCR)
    ↓
PostgreSQL → base colegio_tecnicos (datos estructurados)
Qdrant → colección actas_colegio (chunks para RAG)
```

---

## Stack de infraestructura

Todo corre en Kubernetes, namespace `rag-system`:

| Servicio | ClusterIP | Puerto | Uso |
|----------|-----------|--------|-----|
| docling | 172.20.8.192 | 5001 | Extracción Markdown de PDFs |
| bedrock-gateway | 172.20.22.65 | 80 | Proxy OpenAI-compatible para Claude |
| postgres | 172.20.241.160 | 5432 | Base de datos estructurada |
| qdrant-service | 172.20.186.26 | 6333 | Vector store para RAG |
| open-webui-service | 172.20.32.35 | 80 | Interfaz conversacional |

**Bedrock gateway:** OpenAI-compatible proxy  
**API Key:** `bedrock-gateway-internal-key-2026`  
**Modelo Claude:** `us.anthropic.claude-sonnet-4-20250514-v1:0`  
**Modelo embeddings:** `amazon.titan-embed-text-v2:0` (1024 dimensiones)

**PostgreSQL:**  
- URL: `postgresql://ragsystemuser:admin123@postgres:5432/colegio_tecnicos`  
- Base OpenWebUI (NO tocar): `ragsystemdb`  
- Base del proyecto: `colegio_tecnicos`

---

## Archivos del proyecto

```
ingest/
    ingest.py           # Entry point — recibe PDF como argumento
    extractor.py        # Llama a Docling y Claude
    db.py               # Inserta en PostgreSQL
    qdrant_index.py     # Indexa en Qdrant
    prompts.py          # 6 prompts de extracción
    normalizer.py       # Corrige errores OCR
    .env                # Variables de entorno (dev)
    requirements.txt    # Dependencias Python
    test_sin_docling.py # Test que saltea Docling, usa /tmp/acta_875.md
    venv/               # Virtualenv Python
```

---

## Schema PostgreSQL (base: colegio_tecnicos)

- `actas` — metadatos de cada sesión
- `notas_ingresadas` — cada nota de cada sección del acta
- `personas_mencionadas` — técnicos mencionados, con matrícula
- `expedientes_mencionados` — expedientes referenciados
- `resoluciones_distritales` — resoluciones de cancelación/rehabilitación
- `temas_varios` — puntos del orden del día

---

## Estrategia de extracción (5 llamadas a Claude por acta)

| Llamada | Prompt | max_tokens | Contenido |
|---------|--------|------------|-----------|
| 1 | PROMPT_METADATOS_Y_ME | 4096 | Metadatos del acta + Notas ME y MT |
| 2a | PROMPT_DISTRITOS_1_4 | 6144 | Notas Distrito I, II, III y IV |
| 2b | PROMPT_DISTRITOS_5_7 | 4096 | Notas Distrito V, VI y VII |
| 3 | PROMPT_AS_AT | 6144 | Notas AS y AT |
| 4 | PROMPT_TEMAS_VARIOS | 2048 | Temas varios |

**Costo estimado por acta:** ~$0.08  
**Carga histórica 500 actas:** ~$40

---

## Estado actual al cierre de sesión

### ✅ Completado y funcionando
- Virtualenv configurado
- Dependencias instaladas (`requirements.txt`)
- PostgreSQL: base `colegio_tecnicos` creada con todas las tablas e índices
- Qdrant: colección `actas_colegio` creada (1024 dims, cosine)
- Bedrock gateway: conectado y respondiendo
- Script de ingesta: corre de punta a punta
- Test con Acta 875 exitoso: 72 notas, 6 temas varios, 78 chunks en Qdrant

### 🔧 Problema pendiente — matrículas truncadas
**Síntoma:** Claude devuelve `T-43` en vez de `T-43.822`, `T-35` en vez de `T-35.269`.  
**Causa:** Claude interpreta el punto como separador y trunca el número.  
**Solución diseñada pero NO implementada aún:**  
Agregar función `completar_matricula()` en `normalizer.py` que busca la matrícula truncada en el markdown fuente y la completa.  
El nuevo `normalizer.py` ya está escrito pero falta:
1. Reemplazar el archivo `normalizer.py` con la versión nueva
2. Actualizar `extractor.py` para pasar `markdown` como argumento a `normalizar_nota(n, markdown)`
3. Verificar firma de `extraer_datos` recibe y propaga el markdown
4. Limpiar datos incorrectos de la base y re-correr el test

**Comando para limpiar la base antes de re-correr:**
```bash
python3 -c "
from db import get_connection
conn = get_connection()
cur = conn.cursor()
cur.execute('DELETE FROM resoluciones_distritales')
cur.execute('DELETE FROM expedientes_mencionados')
cur.execute('DELETE FROM personas_mencionadas')
cur.execute('DELETE FROM temas_varios')
cur.execute('DELETE FROM notas_ingresadas')
cur.execute('DELETE FROM actas')
conn.commit()
print('Tablas limpiadas')
conn.close()
"
```

### ⏳ Pendiente — Docling no disponible
El nodo spot de GPU donde corre Docling no está disponible. Cuando esté disponible, probar `ingest.py` con el PDF real (`ACTA_875_FIRMADA.pdf`).

### ⏳ Pendiente — No iniciado
- Function router en OpenWebUI (intercepta preguntas, decide SQL vs RAG vs híbrido)
- Script de producción (variables de entorno apuntando a servicios internos del cluster, sin port-forwards)
- Documentación de despliegue

---

## Para retomar la sesión

### 1. Activar virtualenv y port-forwards
```bash
cd ~/staging/openwui-test/scripts/ingest
source venv/bin/activate

kubectl port-forward -n rag-system svc/docling 5001:5001 &
kubectl port-forward -n rag-system svc/bedrock-gateway 8080:80 &
kubectl port-forward -n rag-system svc/postgres 5432:5432 &
kubectl port-forward -n rag-system svc/qdrant-service 6333:6333 &
```

### 2. Verificar que los servicios responden
```bash
python3 -c "from db import get_connection; conn = get_connection(); print('PG OK'); conn.close()"
python3 -c "from qdrant_client import QdrantClient; q = QdrantClient('http://localhost:6333'); print('Qdrant OK:', [c.name for c in q.get_collections().collections])"
```

### 3. Primer tarea: resolver matrículas truncadas
Ver sección "Problema pendiente" arriba. El nuevo `normalizer.py` ya fue escrito en la conversación, solo falta aplicarlo.

### 4. Archivo de test
El markdown del Acta 875 está en `/tmp/acta_875.md` (se pierde si el servidor reinicia).  
Si no está, regenerarlo con:
```bash
# El heredoc con el contenido está en la conversación de Claude
# Buscar: "cat > /tmp/acta_875.md << 'ENDOFMARKDOWN'"
```

---

## Próximos pasos (en orden)

1. **Resolver matrículas truncadas** — implementar `completar_matricula()` en normalizer
2. **Probar con PDF real** — cuando Docling esté disponible, correr `python3 ingest.py ACTA_875_FIRMADA.pdf`
3. **Construir el router** — Function en OpenWebUI que clasifica preguntas y consulta PostgreSQL o Qdrant
4. **Configuración de producción** — variables de entorno para servicios internos del cluster
5. **Documentación final** — guía de operación para el equipo

---

## Notas técnicas importantes

- El gateway de Bedrock usa modelo default `anthropic.claude-sonnet-4-20250514-v1:0` pero hay que usar el prefijo regional `us.` → `us.anthropic.claude-sonnet-4-20250514-v1:0`
- Docling corre con EasyOCR en GPU, soporte español nativo (`spa,eng`)
- Docling endpoint: `POST /v1alpha/convert/file` con `to_formats=md`
- La base `ragsystemdb` es de OpenWebUI — no agregar tablas ahí
- El Distrito V no tuvo notas en el Acta 875 (es normal, puede variar por acta)
- AT 06/24 y AT 07/24 tenían códigos corruptos en el OCR original (`/ATOi !4`, `ATC :4`) — el normalizador los corrige
