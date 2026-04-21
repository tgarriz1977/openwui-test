# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# RAG System - OpenWebUI on EKS

## Proyecto

Sistema RAG (Retrieval-Augmented Generation) desplegado en un cluster EKS (`colegio-staging`) en `us-east-2`, gestionado con **Kustomize** y **ArgoCD** (GitOps).

- **URL**: https://asistente.tecnicos.org.ar
- **Namespace**: `rag-system`
- **Cluster**: `colegio-staging` (EKS, 2 nodos c5.2xlarge, 50GB root cada uno)
- **Repo**: `git@github.com:tgarriz1977/openwui-test.git` (branch: `main`)

## Arquitectura

```
Internet
  │
  ▼
NGINX Ingress (TLS via cert-manager / Let's Encrypt)
  │
  ▼
OpenWebUI (:8080) ──► Bedrock Gateway (:80) ──► AWS Bedrock (LLM / Embeddings)
  │                         ▲
  ├──► Pipelines (:9099) ───┘   # Query Router: clasifica con Haiku, consulta PG + Qdrant
  │
  ├──► Qdrant (:6333/:6334)     # Base de datos vectorial
  ├──► PostgreSQL (:5432)        # Base de datos relacional (colegio_tecnicos)
  └──► Docling (:5001)           # OCR/parsing — GPU burst bajo demanda (ver GPU-BURST.md)
```

## Componentes activos

| Componente | Tipo | Imagen | Storage |
|---|---|---|---|
| OpenWebUI | Deployment (1 replica) | `ghcr.io/open-webui/open-webui:v0.8.12` | PVC 20Gi gp3-delete |
| Pipelines | Deployment (1 replica) | `ghcr.io/open-webui/pipelines:main` | PVC 5Gi gp3-delete |
| PostgreSQL | StatefulSet (1 replica) | `postgres:16-alpine` | PVC 20Gi gp3-delete |
| Qdrant | Deployment (1 replica) | `qdrant/qdrant:v1.16` | PVC 20Gi gp3-delete |
| Docling GPU | Deployment (**0 replicas** en reposo) | `982170164096.dkr.ecr.us-east-2.amazonaws.com/docling-serve-gpu:latest` | Sin storage |
| Bedrock Gateway | Deployment (1 replica) | `982170164096.dkr.ecr.us-east-2.amazonaws.com/bedrock-access-gateway:latest` | Sin storage |

> Las versiones de OpenWebUI y Qdrant están fijadas en `kustomization.yaml` via `images:`. El tag en los YAMLs puede diferir; `kustomization.yaml` es la fuente de verdad.

> Docling vive en `replicas: 0` permanentemente. Se levanta bajo demanda con GPU para OCR masivo. Ver `GPU-BURST.md`.

## Manifiestos Kustomize (activos)

| Archivo | Contenido |
|---|---|
| `kustomization.yaml` | Raíz Kustomize — define recursos activos y overrides de imágenes |
| `01-storage.yaml` | PVCs de Qdrant y OpenWebUI (gp3-delete, RWO) |
| `02-qdrant.yaml` | Deployment + Service de Qdrant |
| `03-secrets.yaml` | Secret `openwebui-secret` (WEBUI_SECRET_KEY) |
| `04-openwebui.yaml` | Deployment + Service + Ingress (TLS) de OpenWebUI |
| `06-pipeline.yaml` | Deployment + Service + PVC + Secret del servidor de Pipelines |
| `07-docling-gpu.yaml` | Deployment (`replicas:0`) de Docling GPU — **NO incluido en kustomization.yaml**, se aplica manualmente via `gpu-burst-start.sh` |
| `07-docling-service.yaml` | Service de Docling (siempre activo, rutea al pod GPU cuando existe) |
| `09-postgresql.yaml` | PVC + Secret + StatefulSet + ConfigMap init + Services de PostgreSQL |
| `bedrock-gw/bedrock-gateway-secret.yaml` | Secret con API key del Bedrock Gateway |
| `bedrock-gw/bedrock-gateway-deployment.yaml` | Deployment + Service del Bedrock Gateway |

### Archivos inactivos (no incluidos en kustomization.yaml)

| Archivo | Estado |
|---|---|
| `05-hpa.yaml` | HPA, deshabilitado (single replica) |
| `07-docling.yaml` | CPU Docling descartado (calidad insuficiente) |
| `08-redis.yaml` | Redis, removido (innecesario con single replica) |

## Pipeline — Query Router

El pipeline `pipelines/query_router.py` intercepta cada mensaje del usuario en OpenWebUI antes de que llegue al LLM. Funciona como filtro inlet/outlet:

### Inlet (pre-proceso)
1. **Clasificación** con Claude Haiku via Bedrock Gateway — decide qué fuentes consultar y extrae filtros (matrícula, nombre, número de acta, distrito, sección, fechas)
2. **Consulta PostgreSQL** (`colegio_tecnicos`) si `usar_pg=true` — busca por nombre, matrícula, acta, resolución distrital o sección
3. **Búsqueda semántica en Qdrant** (`actas_colegio`) si `usar_qdrant=true` — genera embedding con Titan v2 y busca los top-8 chunks
4. **Inyecta el contexto** en el mensaje del usuario antes de enviarlo al LLM principal (Claude Sonnet 4.6)

### Outlet (post-proceso)
Agrega un bloque **📎 Fuentes** al final de la respuesta del LLM con links clickables a los PDFs de las actas citadas, leídos de `actas.pdf_url` en PostgreSQL.

### Variables de entorno del pipeline
| Variable | Valor | Descripción |
|---|---|---|
| `DATABASE_URL` | `postgresql://ragsystemuser:admin123@postgres:5432/colegio_tecnicos` | PostgreSQL actas |
| `BEDROCK_URL` | `http://bedrock-gateway.rag-system.svc.cluster.local:80` | Bedrock Gateway |
| `BEDROCK_API_KEY` | (desde secret `bedrock-gateway-secret`) | API key del gateway |
| `BEDROCK_MODEL` | `global.anthropic.claude-sonnet-4-6` | LLM principal |
| `CLASSIFIER_MODEL` | `global.anthropic.claude-haiku-4-5-20251001-v1:0` | Modelo clasificador (más rápido) |
| `QDRANT_URL` | `http://qdrant-service.rag-system.svc.cluster.local:6333` | Qdrant |
| `QDRANT_COLLECTION` | `actas_colegio` | Colección vectorial |

### Desplegar cambios al pipeline
```bash
# Copiar al pod (recarga en caliente sin reiniciar)
kubectl cp pipelines/query_router.py \
  rag-system/$(kubectl get pod -n rag-system -l app=pipelines -o jsonpath='{.items[0].metadata.name}'):/app/pipelines/query_router.py

# Si no recarga: reiniciar el deployment
kubectl rollout restart deployment/pipelines -n rag-system

# Ver logs del pipeline
kubectl logs -n rag-system -l app=pipelines -f
```

## Bases de datos PostgreSQL

Hay **dos bases** en el mismo StatefulSet `postgresql-0`:

| Base | Uso | Quién la usa |
|---|---|---|
| `ragsystemdb` | Base interna de OpenWebUI (usuarios, chats, knowledge, files) | OpenWebUI — NO TOCAR |
| `colegio_tecnicos` | Actas estructuradas del Colegio de Técnicos PBA | Pipeline query_router, scripts de ingesta |

### Schema de `colegio_tecnicos`

- `actas` — metadatos de cada sesión (numero, tipo, fecha, participantes, pdf_url)
- `notas_ingresadas` — cada nota de cada sección del acta
- `personas_mencionadas` — técnicos mencionados en notas, con matrícula
- `expedientes_mencionados` — expedientes referenciados en notas
- `resoluciones_distritales` — resoluciones de cancelación/rehabilitación por distrito
- `temas_varios` — puntos del orden del día

> `actas.pdf_url` se popula con `scripts/populate_pdf_urls.py` leyendo la tabla `file` de `ragsystemdb` (OpenWebUI Knowledge collection `be60e885-d097-486c-8d5e-7f6b3049244d`).

## Conexiones entre servicios

- **OpenWebUI → PostgreSQL**: `postgresql://ragsystemuser:admin123@postgres:5432/ragsystemdb`
- **OpenWebUI → Pipelines**: `http://pipelines-service:9099` (API key: `0p3n-w3bu!`)
- **OpenWebUI → Qdrant**: `http://qdrant-service:6333`
- **OpenWebUI → Bedrock Gateway**: `http://bedrock-gateway.rag-system.svc.cluster.local:80/api/v1`
- **OpenWebUI → Docling**: `http://docling:5001` — sin pods en reposo, OCR falla gracefully
- **Pipelines → PostgreSQL**: `postgresql://ragsystemuser:admin123@postgres:5432/colegio_tecnicos`
- **Pipelines → Qdrant**: `http://qdrant-service.rag-system.svc.cluster.local:6333`
- **Pipelines → Bedrock Gateway**: `http://bedrock-gateway.rag-system.svc.cluster.local:80`
- **Bedrock Gateway → AWS Bedrock**: via IRSA (ServiceAccount `openwebui-bedrock-sa`)

## Bedrock Gateway y IRSA

El `bedrock-gateway` y `open-webui` comparten el ServiceAccount `openwebui-bedrock-sa`, con IAM Role via IRSA para invocar modelos en AWS Bedrock. Archivos de referencia en `bedrock/` (excluido de git).

**Modelos Bedrock habilitados**:
- LLM principal: `global.anthropic.claude-sonnet-4-6` (cross-region inference)
- Clasificador pipeline: `global.anthropic.claude-haiku-4-5-20251001-v1:0` (cross-region inference)
- Embeddings: `amazon.titan-embed-text-v2:0` / `cohere.embed-v4:0` (us-east-2)
- Reranking: `cohere.rerank-v3-5:0` (us-east-1 — región diferente)

**Rebuild imagen Bedrock Gateway** (cuando cambia `bedrock-gw/bedrock-access-gateway/src/`):
```bash
aws ecr get-login-password --region us-east-2 | docker login --username AWS --password-stdin 982170164096.dkr.ecr.us-east-2.amazonaws.com
docker build -t bedrock-access-gateway bedrock-gw/bedrock-access-gateway/src/
docker tag bedrock-access-gateway:latest 982170164096.dkr.ecr.us-east-2.amazonaws.com/bedrock-access-gateway:latest
docker push 982170164096.dkr.ecr.us-east-2.amazonaws.com/bedrock-access-gateway:latest
```

## Docling GPU (OCR bajo demanda)

Docling corre en GPU para OCR de calidad, pero en `replicas: 0` para no pagar por el nodo en reposo. Ver `GPU-BURST.md` para el proceso completo.

**Rebuild imagen GPU** (cuando cambia `docker/docling-gpu/`):
```bash
cd docker/docling-gpu && ./build-and-push.sh
# Imagen: 982170164096.dkr.ecr.us-east-2.amazonaws.com/docling-serve-gpu:latest
```

**Activar/desactivar OCR**:
```bash
./scripts/gpu-burst-start.sh   # levanta nodo g4dn.xlarge spot + docling GPU (~$0.17/hr)
./scripts/gpu-burst-stop.sh    # baja docling + termina nodo ($0)
```

### Nodegroups GPU disponibles

| Nodegroup | Tipo | Instance | Costo | Cuándo usarlo |
|---|---|---|---|---|
| `gpu-spot` | SPOT | g4dn.xlarge | ~$0.17/hr | Default — OCR rutinario |
| `gpu-ondemand` | ON_DEMAND | g4dn.xlarge | ~$0.53/hr | Fallback cuando spot sufre `UnfulfillableCapacity` o reclaims continuos |

**Alternar entre spot y on-demand**:
```bash
# Pasar a on-demand
aws eks update-nodegroup-config --cluster-name colegio-staging --region us-east-2 \
  --nodegroup-name gpu-spot     --scaling-config minSize=0,maxSize=1,desiredSize=0
aws eks update-nodegroup-config --cluster-name colegio-staging --region us-east-2 \
  --nodegroup-name gpu-ondemand --scaling-config minSize=0,maxSize=1,desiredSize=1

# Volver a spot
aws eks update-nodegroup-config --cluster-name colegio-staging --region us-east-2 \
  --nodegroup-name gpu-ondemand --scaling-config minSize=0,maxSize=1,desiredSize=0
aws eks update-nodegroup-config --cluster-name colegio-staging --region us-east-2 \
  --nodegroup-name gpu-spot     --scaling-config minSize=0,maxSize=1,desiredSize=1
```

> Mantener **solo uno activo** a la vez.

## Despliegue y GitOps

ArgoCD monitorea `main` y aplica cambios automáticamente. Para emergencias:
```bash
kubectl apply -k .
```

Para actualizar versiones de imágenes públicas, editar `kustomization.yaml` (sección `images:`), no los YAMLs individuales.

## Ingress y TLS

- **Ingress Class**: nginx
- **Certificado**: Let's Encrypt (`letsencrypt-prod` ClusterIssuer via cert-manager)
- **Secret TLS**: `openwebui-tls`
- **SSL Redirect**: habilitado (HTTP → HTTPS 308)
- **Proxy timeouts**: 600s (lectura/envío), body size max 100m

## Storage y Backups

Todos los PVCs usan `gp3-delete` (EBS gp3 con reclaim policy Delete). Backups gestionados con **Velero**. No usar `gp3-retain` — genera volúmenes huérfanos dado que Velero cubre los backups.

## Decisiones de diseño

1. **gp3-delete en vez de gp3-retain**: Con Velero manejando backups, gp3-retain genera volúmenes huérfanos innecesarios.
2. **Sin Redis**: Con single replica no se necesita Redis para coordinar WebSockets ni sesiones.
3. **PostgreSQL como DB**: Reemplaza SQLite. Dos Services: `postgres` (ClusterIP, para la app) y `postgresql-service` (headless, para el StatefulSet).
4. **ServiceAccount `openwebui-bedrock-sa`**: Compartido entre OpenWebUI y Bedrock Gateway. Acceso a AWS Bedrock via IRSA.
5. **Docling GPU burst, no CPU permanente**: CPU Docling (Tesseract) descartado por calidad insuficiente. GPU en nodo spot bajo demanda a ~$0.17/hr.
6. **Haiku para clasificador, Sonnet para respuesta**: El pipeline usa Haiku en la clasificación (tarea simple, baja latencia) y Sonnet 4.6 para la respuesta final.
7. **pdf_url en PostgreSQL**: Las URLs de los PDFs se almacenan en `actas.pdf_url` leyendo de `ragsystemdb.file` una vez, en vez de consultar la API de OpenWebUI en cada request.

## Comandos útiles

```bash
# Ver pods
kubectl get pods -n rag-system

# Logs
kubectl logs -n rag-system -l app=open-webui -f
kubectl logs -n rag-system -l app=pipelines -f
kubectl logs -n rag-system -l app=postgresql -f
kubectl logs -n rag-system -l app=bedrock-gateway -f

# Estado de certificados TLS
kubectl get certificate -n rag-system

# Conectarse a PostgreSQL (actas)
kubectl exec -n rag-system postgresql-0 -- psql -U ragsystemuser -d colegio_tecnicos

# Conectarse a PostgreSQL (OpenWebUI)
kubectl exec -n rag-system postgresql-0 -- psql -U ragsystemuser -d ragsystemdb

# Reiniciar deployments
kubectl rollout restart deployment/open-webui -n rag-system
kubectl rollout restart deployment/pipelines -n rag-system

# Verificar IRSA
kubectl exec -n rag-system deployment/bedrock-gateway -- env | grep AWS

# Repoblar pdf_url tras subir nuevos PDFs a Knowledge
cd scripts/ingest && source venv/bin/activate
python3 ../populate_pdf_urls.py
```
