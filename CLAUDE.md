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
OpenWebUI (:8080) ──► Bedrock Gateway (:80) ──► AWS Bedrock (LLM)
  │
  ├──► Qdrant (:6333/:6334)     # Base de datos vectorial
  ├──► PostgreSQL (:5432)        # Base de datos relacional
  ├──► Docling (:5001)           # OCR/parsing de documentos
  └──► Pipelines (:9099)         # Pipelines personalizados (deshabilitado)
```

## Componentes activos

| Componente | Tipo | Imagen | Storage |
|---|---|---|---|
| OpenWebUI | Deployment (1 replica) | `ghcr.io/open-webui/open-webui:main` | PVC 20Gi gp3-delete |
| PostgreSQL | StatefulSet (1 replica) | `postgres:16-alpine` | PVC 20Gi gp3-delete |
| Qdrant | Deployment (1 replica) | `qdrant/qdrant:v1.16` | PVC 20Gi gp3-delete |
| Docling | Deployment (1 replica) | `quay.io/docling-project/docling-serve` | Sin storage |

## Manifiestos Kustomize

| Archivo | Contenido |
|---|---|
| `01-storage.yaml` | PVCs de Qdrant y OpenWebUI (gp3-delete, RWO) |
| `02-qdrant.yaml` | Deployment + Service de Qdrant |
| `03-secrets.yaml` | Secret `openwebui-secret` (WEBUI_SECRET_KEY) |
| `04-openwebui.yaml` | Deployment + Service + Ingress (TLS) de OpenWebUI |
| `07-docling.yaml` | Deployment + Service de Docling (CPU, Tesseract OCR) |
| `09-postgresql.yaml` | PVC + Secret + StatefulSet + ConfigMap init + Services de PostgreSQL |

### Archivos inactivos (no incluidos en kustomization.yaml)

| Archivo | Estado |
|---|---|
| `05-hpa.yaml` | HPA, deshabilitado (single replica) |
| `06-pipeline.yaml` | Pipelines, deshabilitado |
| `07-docling-gpu.yaml` | Versión GPU de Docling, no activa |
| `08-redis.yaml` | Redis, removido (innecesario con single replica) |

## Conexiones entre servicios

- **OpenWebUI → PostgreSQL**: `postgresql://ragsystemuser:admin123@postgres:5432/ragsystemdb` (via secret `postgresql-secret`)
- **OpenWebUI → Qdrant**: `http://qdrant-service:6333`
- **OpenWebUI → Bedrock Gateway**: `http://bedrock-gateway.rag-system.svc.cluster.local:80/api/v1`
- **OpenWebUI → Docling**: Configurado desde la UI de OpenWebUI (puerto 5001)

## Ingress y TLS

- **Ingress Class**: nginx
- **Certificado**: Let's Encrypt (`letsencrypt-prod` ClusterIssuer via cert-manager)
- **Secret TLS**: `openwebui-tls`
- **SSL Redirect**: habilitado (HTTP → HTTPS 308)
- **Proxy timeouts**: 600s (lectura/envío), body size max 100m

## Storage

Todos los PVCs usan `gp3-delete` (EBS gp3 con reclaim policy Delete). Backups gestionados con **Velero**.

## Infraestructura

- **Nodos**: 2x `c5.2xlarge` (8 vCPU, 16GB RAM, 50GB root EBS gp3)
- **Region**: us-east-2
- **Backups**: Velero
- **GitOps**: ArgoCD (app: `asistente`)

## Decisiones de diseño

1. **gp3-delete en vez de gp3-retain**: Con Velero manejando backups, gp3-retain genera volúmenes huérfanos innecesarios.
2. **Sin Redis**: Con single replica no se necesita Redis para coordinar WebSockets ni sesiones.
3. **PostgreSQL como DB**: Reemplaza SQLite para soporte de escalado horizontal futuro.
4. **ServiceAccount `openwebui-bedrock-sa`**: Permite acceso a AWS Bedrock via IRSA.
5. **Docling CPU (no GPU)**: Usa Tesseract OCR en modo CPU. La imagen es pesada (~3GB+).

## Comandos útiles

```bash
# Ver pods
kubectl get pods -n rag-system

# Logs de OpenWebUI
kubectl logs -n rag-system -l app=open-webui -f

# Logs de PostgreSQL
kubectl logs -n rag-system -l app=postgresql -f

# Estado de certificados
kubectl get certificate -n rag-system

# Aplicar cambios con kustomize (lo hace ArgoCD automáticamente)
kubectl apply -k .

# Verificar conectividad PostgreSQL
kubectl exec -n rag-system postgresql-0 -- pg_isready -U ragsystemuser -d ragsystemdb
```
