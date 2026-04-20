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

## Estado actual al cierre de sesión — 2026-04-17

### ✅ Completado y funcionando
- Virtualenv configurado, dependencias instaladas
- PostgreSQL: base `colegio_tecnicos` con todas las tablas e índices
- Qdrant: colección `actas_colegio` poblada (1024 dims, cosine) — **ver decisión abajo, probablemente se descarta**
- Bedrock gateway conectado (Claude Sonnet 4 + Titan embed v2)
- Docling GPU funcionando (endpoint `/v1/convert/file`, con `image_export_mode=placeholder` para evitar markdown hinchado)
- **Carga masiva 2024 completa: 63 actas ingresadas** — 51 Mesa Ejecutiva (874-924) + 12 Consejo Superior (609-620)
- **Matrículas truncadas RESUELTO**: `completar_matricula()` en `normalizer.py` aplicado; propaga markdown a través de `normalizar_nota(n, markdown)`
- `max_tokens=32768` en las 5 llamadas a Claude (antes variaban 2048–16384 y truncaban con actas grandes)
- Bug menor fixeado: label `"metadatos y ME/MT"` contenía `/` y rompía el path del archivo de debug, ocultando errores de truncación → ahora `"metadatos y ME-MT"`
- Nodegroups GPU: `gpu-spot` (default) y `gpu-ondemand` (fallback para cuando spot falla por `UnfulfillableCapacity`). Ambos con label `node-type=gpu` y taint `nvidia.com/gpu:NoSchedule` (compatible con NVIDIA device plugin). Ver `/home/admin/staging/openwui-test/CLAUDE.md` sección Docling GPU.
- **Log de ingesta**: `ingest.py` registra cada acta procesada (OK o ERROR) en `/home/admin/staging/openwui-test/ingesta-log.md` — tabla markdown con fecha, archivo, número de acta, DB id, notas extraídas, tiempo y estado. El log se mantiene deduplicado por archivo (una fila OK por acta).
- **Retry + reparación de JSON**: `extractor.py` intenta reparar JSON truncado (cerrando brackets faltantes) y si falla reintenta la llamada a Claude una vez antes de abortar.
- **Detección de tipo de acta**: `ingest.py` detecta CS/ME desde el nombre del archivo (`ACTA_CS_` → "Consejo Superior", `ACTA_ME_` → "Mesa Ejecutiva") y lo pasa a la DB. `db.py` setea `actas.tipo` en el INSERT/UPDATE.
- **Test function calling vía Bedrock Gateway: OK** — el gateway propaga correctamente `tools` y `tool_choice` al protocolo OpenAI. Confirmado con prompt mínimo `get_weather`. La opción 3 (tool de PostgreSQL) es viable.
- **Docling timeout aumentado a 600s** (antes 120s) — algunas actas grandes lo excedían.
- **Schema DB ampliado**: se cambiaron a `TEXT` las columnas que fallaban con `varchar(100)`: `expedientes_mencionados.referencia_ctd`, `expedientes_mencionados.numero_expediente`, `personas_mencionadas.rol_mencion`, `resoluciones_distritales.numero_resolucion`, `resoluciones_distritales.tipo_resolucion`, `notas_ingresadas.seccion`.
- **Sanitización de expedientes/personas**: `db.py` acepta strings sueltos (no solo dicts) en `expedientes` y `personas` — Claude a veces devuelve `expedientes: ["AT N°338/24"]` en vez de `[{numero_expediente: ...}]`.

### ⚠️ Observación operativa — scheduler EKS
El Lambda `eks-scheduler-start` (07:00 ART) escala **todos los managed nodegroups** del cluster a `desiredSize>=2`, incluyendo `gpu-ondemand`. Esto hace que aparezcan nodos GPU costosos sin uso real. Acción manual al terminar ingesta: bajar `gpu-ondemand` a `minSize=0,desiredSize=0`. **Pendiente:** revisar el código del Lambda para que ignore los nodegroups GPU.

### 🔑 Decisión de arquitectura tomada — Opción 3 (híbrida)

Para la capa de consulta en OpenWebUI vamos a implementar un **esquema híbrido**:

1. **OpenWebUI Knowledge** (flujo RAG nativo) con el markdown de cada acta + el PDF original adjunto → da citaciones automáticas con link clickable al PDF. **Esto reemplaza al Qdrant custom.**
2. **PostgreSQL** expuesto como **Tool** (function calling) → el LLM (Sonnet 4) decide cuándo invocarla para consultas estructuradas (conteos, filtros por distrito/matrícula/tipo, lookups de personas).
3. **Sin router clasificador**: el modelo decide turno a turno si usar solo el RAG nativo inyectado o además llamar a la tool. Guiado por la **descripción de la tool** (docstring explícito con cuándo usarla y cuándo no).

**Por qué descartamos opción 1 (solo Knowledge nativo):** chunks "tontos" sin control de metadata por nota/matrícula/distrito.
**Por qué descartamos opción 2 (Qdrant custom + citaciones reimplementadas):** habría que reconstruir a mano storage de PDFs, URLs, citaciones, seguimiento — trabajo que OpenWebUI ya resuelve.

### ⚠️ Qdrant custom queda deprecado
En opción 3 el semántico lo hace Knowledge de OpenWebUI. **Plan para mañana:**
- Eliminar `qdrant_index.py` del pipeline de ingesta
- Borrar la colección `actas_colegio` de Qdrant
- La instancia de Qdrant sigue en pie porque OpenWebUI Knowledge la usa internamente, **no tocar el servicio**

### ⚠️ Caveat a verificar antes de construir la tool
El **Bedrock Gateway** tiene que propagar correctamente los parámetros `tools` y `tool_choice` del protocolo OpenAI hacia Bedrock. Si no los propaga, las tools no llegan al modelo y la opción 3 no funciona. **Antes de invertir tiempo en el schema de la tool, hacer un test mínimo de function calling vía el gateway.**

### 🎯 Próximos pasos (en orden) — para retomar mañana

1. **Test function calling a través de Bedrock Gateway** (bloqueante).
   Script mínimo: un `client.chat.completions.create()` con un `tools=[{...}]` trivial (ej. `get_weather`) y verificar que el response trae `tool_calls`. Si falla, hay que parchar el gateway.

2. **Modificar el pipeline de ingesta para guardar markdown + subirlo a OpenWebUI Knowledge**:
   - En `ingest.py`, después de `pdf_a_markdown()`, guardar el markdown a `/tmp/actas-colegio/ActasColegio/2024/ACTA_NNN.md`
   - Agregar paso nuevo: `POST` al endpoint de Knowledge de OpenWebUI con el **PDF como `file`** y el **markdown como `content`** (OpenWebUI permite subir archivo + contenido extraído manualmente, así el usuario ve el PDF y el RAG usa el chunking de calidad de docling)
   - Endpoint a investigar: `POST /api/v1/files/` y `POST /api/v1/knowledge/{id}/file/add`
   - Eliminar el paso de `qdrant_index.py`

3. **Reprocesar las 4 actas ya ingresadas** contra OpenWebUI Knowledge. PostgreSQL ya está poblado con ellas, así que el ingest tendría que ser idempotente (o saltear el paso DB si ya existe el `numero_acta`). Alternativa simple: limpiar PG y reprocesar end-to-end las 4.

4. **Borrar colección `actas_colegio` de Qdrant** una vez confirmado que Knowledge funciona.

5. **Construir la Tool** en OpenWebUI que consulta PostgreSQL:
   - Funciones mínimas: `buscar_notas_estructurado(distrito, tipo, matricula, numero_acta)`, `contar_notas_por_acta(numero_acta)`, `buscar_persona_por_matricula(matricula)`
   - Docstrings explícitos sobre cuándo SÍ y cuándo NO usarlas
   - Registrar como Tool en OpenWebUI (no como Function)

6. **Carga histórica de las ~500 actas restantes** una vez validado el pipeline nuevo.

7. **Config de producción** — env vars apuntando a servicios internos del cluster, sin port-forwards.

8. **Documentación de operación** para el equipo.

---

## Para retomar la sesión mañana

### 1. Estado del cluster
- `gpu-ondemand` escalado a **0** al cierre (sin costo GPU corriendo)
- `docling-gpu` deployment escalado a **0**
- Para reprocesar actas o hacer nueva ingesta, levantar GPU:
```bash
aws eks update-nodegroup-config --cluster-name colegio-staging --region us-east-2 \
  --nodegroup-name gpu-ondemand --scaling-config minSize=0,maxSize=1,desiredSize=1
# esperar a que el nodo esté Ready
kubectl scale deployment/docling-gpu -n rag-system --replicas=1
```
(O usar `gpu-spot` si hay capacidad. Ver sección Docling GPU en `/home/admin/staging/openwui-test/CLAUDE.md`.)

### 2. Activar virtualenv y port-forwards
```bash
cd ~/staging/openwui-test/scripts/ingest
source venv/bin/activate

kubectl port-forward -n rag-system svc/docling 5001:5001 &
kubectl port-forward -n rag-system svc/bedrock-gateway 8080:80 &
kubectl port-forward -n rag-system svc/postgres 5432:5432 &
kubectl port-forward -n rag-system svc/qdrant-service 6333:6333 &
```

### 3. Verificar estado en la base
```bash
python3 -c "
from db import get_connection
conn = get_connection(); cur = conn.cursor()
cur.execute('SELECT id, numero_acta FROM actas ORDER BY numero_acta')
print(cur.fetchall())
conn.close()
"
# Esperado: [(3, 875), (4, 874), (5, 876), (6, 877)] o similar
```

### 4. Primera tarea concreta mañana
**Test de function calling vía Bedrock Gateway** (paso 1 de próximos pasos). Es bloqueante — si falla, toda la opción 3 necesita replantearse.

---

## Notas técnicas importantes

- El gateway de Bedrock usa modelo default `anthropic.claude-sonnet-4-20250514-v1:0` pero hay que usar el prefijo regional `us.` → `us.anthropic.claude-sonnet-4-20250514-v1:0`
- Docling corre con EasyOCR en GPU, soporte español nativo (`spa,eng`)
- Docling endpoint: `POST /v1alpha/convert/file` con `to_formats=md`
- La base `ragsystemdb` es de OpenWebUI — no agregar tablas ahí
- El Distrito V no tuvo notas en el Acta 875 (es normal, puede variar por acta)
- AT 06/24 y AT 07/24 tenían códigos corruptos en el OCR original (`/ATOi !4`, `ATC :4`) — el normalizador los corrige
