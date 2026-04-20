# Query Router Pipeline

Filter de OpenWebUI Pipelines que intercepta cada pregunta del chat y la enriquece
con contexto recuperado desde PostgreSQL (datos estructurados) y/o Qdrant
(búsqueda semántica) sobre las actas del Colegio de Técnicos PBA.

## Archivos

- `query_router.py` — el filter. Clase `Pipeline` con `inlet()` async.
- `requirements.txt` — referencia de dependencias (las instala el propio runtime
  vía frontmatter `requirements:` del `.py`).

## Arquitectura

```
OpenWebUI chat → pipelines-service:9099 → query_router.inlet()
  1. Clasifica la pregunta llamando a Claude (Bedrock Gateway) → JSON
     {usar_pg, usar_qdrant, filtros, query_semantica}
  2. Si usar_pg: ejecuta SQL parametrizado sobre colegio_tecnicos
  3. Si usar_qdrant: embedding Titan v2 + búsqueda en actas_colegio
  4. Inyecta el resultado como bloque markdown en el último user message
OpenWebUI → LLM final (Claude Sonnet 4) con el contexto
```

## Variables de entorno (inyectadas por `06-pipeline.yaml`)

- `DATABASE_URL` — DSN a la base `colegio_tecnicos`
- `QDRANT_URL` — `http://qdrant-service:6333`
- `QDRANT_COLLECTION` — `actas_colegio`
- `BEDROCK_URL` — `http://bedrock-gateway.rag-system.svc.cluster.local:80`
- `BEDROCK_API_KEY` — via secret `bedrock-gateway-secret`
- `BEDROCK_MODEL` — `us.anthropic.claude-sonnet-4-20250514-v1:0`

## Valves (ajustables desde la UI)

| Valve | Default | Descripción |
|-------|---------|-------------|
| `pipelines` | `["*"]` | Modelos a los que aplica el filter |
| `priority` | `0` | Orden si hay varios filters |
| `enabled` | `true` | Master switch (rollback sin tocar YAML) |
| `top_k_qdrant` | `8` | Chunks a recuperar en la búsqueda semántica |
| `max_rows_pg` | `30` | Filas máximas por query SQL |
| `classifier_max_tokens` | `512` | Tokens del JSON clasificador |
| `log_clasificacion` | `true` | Logguea el plan del clasificador |

## Despliegue

1. Aplicar manifiestos:
   ```bash
   kubectl apply -k .
   kubectl get pods -n rag-system -l app=pipelines
   kubectl logs -n rag-system deploy/pipelines
   ```

2. Subir el filter al servidor (una vez que el pod está Ready):

   **Opción A — UI**: Admin Settings → Pipelines → Upload `query_router.py`.

   **Opción B — CLI** (requiere port-forward):
   ```bash
   kubectl port-forward -n rag-system svc/pipelines-service 9099:9099
   curl -X POST http://localhost:9099/v1/pipelines/upload \
     -H "Authorization: Bearer 0Pa3n-w3bu!" \
     -F "file=@pipelines/query_router.py"
   ```

3. Verificar en OpenWebUI → Admin → Pipelines que aparece `query_router`.

## Prueba local (sin OpenWebUI)

```bash
cd scripts/ingest && source venv/bin/activate

# Port-forwards
kubectl port-forward -n rag-system svc/postgres 5432:5432 &
kubectl port-forward -n rag-system svc/qdrant-service 6333:6333 &
kubectl port-forward -n rag-system svc/bedrock-gateway 8080:80 &

# Env vars locales
export DATABASE_URL="postgresql://ragsystemuser:admin123@localhost:5432/colegio_tecnicos"
export QDRANT_URL="http://localhost:6333"
export BEDROCK_URL="http://localhost:8080"
export BEDROCK_API_KEY="bedrock-gateway-internal-key-2026"

cd ../../pipelines
python - <<'PY'
import asyncio, json
from query_router import Pipeline
p = Pipeline()
asyncio.run(p.on_startup())
for pregunta in [
    "¿Cuántas notas trató el acta 875?",
    "¿Qué se discutió sobre incumbencias profesionales?",
    "¿Qué resoluciones hubo sobre la matrícula 12345?",
]:
    body = {"messages": [{"role": "user", "content": pregunta}]}
    out = asyncio.run(p.inlet(body))
    print("\n===", pregunta)
    print(out["messages"][-1]["content"][:1200])
PY
```

## Rollback

- Desde la UI: bajar valve `enabled: false`.
- Quitar `06-pipeline.yaml` de `kustomization.yaml` y `kubectl apply -k .`.
