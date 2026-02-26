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
OpenWebUI (:8080) ──► Bedrock Gateway (:80) ──► AWS Bedrock (LLM / Embeddings / Rerank)
  │
  ├──► Qdrant (:6333/:6334)     # Base de datos vectorial
  ├──► PostgreSQL (:5432)        # Base de datos relacional
  └──► Docling (:5001)           # OCR/parsing — GPU burst bajo demanda (ver GPU-BURST.md)
```

## Componentes activos

| Componente | Tipo | Imagen | Storage |
|---|---|---|---|
| OpenWebUI | Deployment (1 replica) | `ghcr.io/open-webui/open-webui:v0.8.3` | PVC 20Gi gp3-delete |
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
| `07-docling-gpu.yaml` | Deployment (`replicas:0`) + Service de Docling GPU |
| `09-postgresql.yaml` | PVC + Secret + StatefulSet + ConfigMap init + Services de PostgreSQL |
| `bedrock-gw/bedrock-gateway-secret.yaml` | Secret con API key del Bedrock Gateway |
| `bedrock-gw/bedrock-gateway-deployment.yaml` | Deployment + Service del Bedrock Gateway |

### Archivos inactivos (no incluidos en kustomization.yaml)

| Archivo | Estado |
|---|---|
| `05-hpa.yaml` | HPA, deshabilitado (single replica) |
| `06-pipeline.yaml` | Pipelines, deshabilitado |
| `07-docling.yaml` | CPU Docling descartado (calidad insuficiente) |
| `08-redis.yaml` | Redis, removido (innecesario con single replica) |

## Conexiones entre servicios

- **OpenWebUI → PostgreSQL**: `postgresql://ragsystemuser:admin123@postgres:5432/ragsystemdb` (via secret `postgresql-secret`)
- **OpenWebUI → Qdrant**: `http://qdrant-service:6333`
- **OpenWebUI → Bedrock Gateway**: `http://bedrock-gateway.rag-system.svc.cluster.local:80/api/v1`
- **OpenWebUI → Docling**: `http://docling:5001` — sin pods en reposo, OCR falla gracefully
- **Bedrock Gateway → AWS Bedrock**: via IRSA (ServiceAccount `openwebui-bedrock-sa`)

## Bedrock Gateway y IRSA

El `bedrock-gateway` y `open-webui` comparten el ServiceAccount `openwebui-bedrock-sa`, con IAM Role via IRSA para invocar modelos en AWS Bedrock. Archivos de referencia en `bedrock/` (excluido de git).

**Modelos Bedrock habilitados**:
- LLM principal: `anthropic.claude-sonnet-4-20250514-v1:0` (us-east-2)
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

## Comandos útiles

```bash
# Ver pods
kubectl get pods -n rag-system

# Logs
kubectl logs -n rag-system -l app=open-webui -f
kubectl logs -n rag-system -l app=postgresql -f
kubectl logs -n rag-system -l app=bedrock-gateway -f

# Estado de certificados TLS
kubectl get certificate -n rag-system

# Verificar conectividad PostgreSQL
kubectl exec -n rag-system postgresql-0 -- pg_isready -U ragsystemuser -d ragsystemdb

# Conectarse a PostgreSQL
kubectl exec -n rag-system postgresql-0 -- psql -U ragsystemuser -d ragsystemdb

# Reiniciar un deployment
kubectl rollout restart deployment/open-webui -n rag-system

# Verificar IRSA
kubectl exec -n rag-system deployment/bedrock-gateway -- env | grep AWS
```
