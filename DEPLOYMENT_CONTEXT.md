# RAG System - Contexto de Despliegue

## Información General del Sistema

### Descripción
Sistema RAG (Retrieval-Augmented Generation) desplegado en Kubernetes que proporciona un chatbot inteligente con capacidades de búsqueda semántica sobre documentos. Utiliza Open WebUI como interfaz, Qdrant como base de datos vectorial, y modelos LLM de Qwen para generación de respuestas y embeddings.

### URL de Acceso
- **Producción**: https://asistente.colegio-tecnicos.edu.ar (configurar según dominio)
- **Namespace**: `rag-system`

---

## Arquitectura de Componentes

### 1. Open WebUI (Frontend y Orquestador)
**Deployment**: `open-webui`
- **Imagen**: `ghcr.io/open-webui/open-webui:main`
- **Puerto**: 8080
- **Escalabilidad**: Horizontal con HPA (1-10 réplicas)
- **Recursos por pod**:
  - Request: 1Gi RAM, 250m CPU
  - Limit: 2Gi RAM, 1 CPU

**Función**: Interfaz web para usuarios, orquestación de consultas RAG, gestión de documentos y conversaciones.

**Almacenamiento**:
- **PVC**: `openwebui-storage` (20Gi, ReadWriteMany, Longhorn)
- **Mount**: `/app/backend/data`
- **Contenido**: Archivos subidos, imágenes generadas, cache

### 2. Qdrant (Vector Database)
**Deployment**: `qdrant`
- **Imagen**: `qdrant/qdrant:latest`
- **Puerto**: 6333
- **Escalabilidad**: Single replica (ReadWriteOnce)
- **Service**: `qdrant-service.rag-system.svc.cluster.local:6333`

**Función**: Almacenamiento y búsqueda de embeddings vectoriales para RAG.

**Almacenamiento**:
- **PVC**: `qdrant-storage` (100Gi, ReadWriteOnce, Longhorn)

### 3. LlamaIndex API
**Deployment**: `llamaindex-api`
- **Puerto**: 8000
- **Service**: `llamaindex-api-service.rag-system.svc.cluster.local:8000`

**Función**: Pipelines personalizados de procesamiento RAG.

**Almacenamiento**:
- **PVC**: `llamaindex-storage` (10Gi, ReadWriteOnce, Longhorn)

---

## Servicios Internos del Sistema

### 1. PostgreSQL (Base de Datos Relacional)
**Deployment**: `postgresql` (StatefulSet)
- **Imagen**: `postgres:16-alpine`
- **Service**: `postgres:5432` / `postgresql-service:5432`
- **Database**: `ragsystemdb`
- **User**: `ragsystemuser`
- **Uso**: Almacenamiento de usuarios, conversaciones, configuraciones, metadatos

**Función Crítica**: Permite escrituras concurrentes de múltiples réplicas de Open WebUI. Reemplaza SQLite que no soporta multi-escritura.

**Almacenamiento**:
- **PVC**: `postgresql-storage` (10Gi, ReadWriteOnce, Longhorn)
- **Extensiones**: uuid-ossp, pg_trgm para búsqueda full-text
- **Timezone**: America/Argentina/Buenos_Aires

**Credenciales** (en secret `postgresql-secret`):
- Usuario aplicación: `ragsystemuser`
- Password: `rag322wq`
- Superusuario postgres: `admin123`

## Servicios Externos Integrados

### 2. Redis (Cache y WebSocket)
**Deployment**: `redis` (StatefulSet)
- **Imagen**: `redis:7-alpine`
- **Service**: `redis-service:6379`
- **Configuración**: Modo standalone, stateless (sin persistencia)

**Bases de datos asignadas**:
- **DB 0**: Cache general de aplicación, sesiones
- **DB 1**: Coordinación de WebSockets entre pods

**Función Crítica**:
- Sincronización de sesiones WebSocket entre réplicas
- Cache compartido de configuraciones
- Notificaciones pub/sub entre pods

**Almacenamiento**:
- Sin PVC (stateless) - La data importante está en PostgreSQL
- Configuración de persistencia deshabilitada para mejor performance

### 3. SimpleVLLM (LLM Principal)
**Namespace**: `simplevllm`
- **Service**: `simplevllm-svc.simplevllm.svc.cluster.local:8000`
- **Modelo**: `Qwen/Qwen2.5-14B-Instruct`
- **Endpoint**: `/v1` (compatible con OpenAI API)

**Función**: Generación de respuestas del chatbot basadas en contexto RAG.

### 4. Qwen Embedding Service
**URL Externa**: `https://qwen-embedding.test.arba.gov.ar/v1`
- **Modelo**: `Qwen/Qwen3-Embedding-0.6B`
- **API Key**: `sk-dummy-key` (configurada en deployment)

**Función**: Generación de embeddings vectoriales para documentos y consultas.

---

## Configuración de Escalado Horizontal

### Horizontal Pod Autoscaler (HPA)
Open WebUI está configurado para escalar automáticamente:
- **Mínimo**: 1 réplica
- **Máximo**: 10 réplicas
- **Métricas**: CPU/Memory basado

### Requisitos para Escalado
1. ✅ **PVC ReadWriteMany**: Permite múltiples pods montar el mismo volumen
2. ✅ **PostgreSQL interno**: Base de datos compartida entre réplicas (StatefulSet)
3. ✅ **Redis interno para WebSocket**: Sincronización de sesiones entre pods
4. ✅ **Secret Key compartida**: Autenticación consistente entre réplicas
5. ✅ **Sticky Sessions**: Afinidad de cookie en Ingress NGINX

---

## Secrets de Kubernetes

### 1. `postgresql-secret` (namespace: rag-system)
```yaml
postgres-password: admin123
postgres-user: ragsystemuser
postgres-password-user: rag322wq
postgres-db: ragsystemdb
database-url: postgresql://ragsystemuser:rag322wq@postgres:5432/ragsystemdb
```
**⚠️ IMPORTANTE**: Cambiar estas contraseñas en producción.

### 2. `redis-config` (namespace: rag-system)
```yaml
websocket-url: redis://redis-service:6379/1
cache-url: redis://redis-service:6379/0
```

### 3. `openwebui-secret` (namespace: rag-system)
```yaml
secret-key: 050cde99ea744214e7b714b7079954eac37a94c5338730a4e6762ba3eba92cb6
```
**⚠️ CRÍTICO**: Esta clave debe ser la misma en todas las réplicas. No cambiarla una vez en producción.

---

## Variables de Entorno Clave

### Configuración LLM
```yaml
OPENAI_API_BASE_URL: http://simplevllm-svc.simplevllm.svc.cluster.local:8000/v1
OPENAI_API_KEY: sk-dummy-key
DEFAULT_MODELS: Qwen/Qwen2.5-14B-Instruct
```

### Configuración Vector DB
```yaml
VECTOR_DB: qdrant
QDRANT_URI: http://qdrant-service:6333
```

### Configuración Embeddings
```yaml
RAG_EMBEDDING_ENGINE: openai
RAG_EMBEDDING_MODEL: Qwen/Qwen3-Embedding-0.6B
RAG_OPENAI_API_BASE_URL: https://qwen-embedding.test.arba.gov.ar/v1
RAG_OPENAI_API_KEY: sk-dummy-key
```

### Configuración RAG
```yaml
CHUNK_SIZE: 1000
CHUNK_OVERLAP: 200
RAG_TOP_K: 20
ENABLE_RAG_HYBRID_SEARCH: True
ENABLE_RAG_WEB_LOADER: True
PDF_EXTRACT_IMAGES: True
```

### Configuración Base de Datos (Multi-replica)
```yaml
DATABASE_URL: postgresql://ragsystemuser:rag322wq@postgres:5432/ragsystemdb
WEBSOCKET_MANAGER: redis
WEBSOCKET_REDIS_URL: redis://redis-service:6379/1
REDIS_URL: redis://redis-service:6379/0
WEBUI_SECRET_KEY: (desde secret openwebui-secret)
```

---

## Configuración de Ingress

### Anotaciones NGINX
```yaml
kubernetes.io/ingress.class: nginx
nginx.ingress.kubernetes.io/proxy-body-size: "100m"        # Permite uploads grandes
nginx.ingress.kubernetes.io/proxy-read-timeout: "600"      # Streaming LLM
nginx.ingress.kubernetes.io/proxy-send-timeout: "600"
nginx.ingress.kubernetes.io/ssl-redirect: "true"
nginx.ingress.kubernetes.io/affinity: "cookie"             # Sticky sessions
nginx.ingress.kubernetes.io/session-cookie-name: "route"
nginx.ingress.kubernetes.io/session-cookie-expires: "172800"  # 48 horas
nginx.ingress.kubernetes.io/session-cookie-max-age: "172800"
```

---

## Flujo de Datos - Query RAG

1. **Usuario envía pregunta** → Ingress NGINX → Open WebUI pod (balanceado)
2. **Open WebUI** verifica sesión → Consulta Redis (WebSocket session)
3. **Generación de embedding** → Qwen Embedding API → Vector de consulta
4. **Búsqueda semántica** → Qdrant → Top 20 documentos relevantes
5. **Construcción de contexto** → Open WebUI + LlamaIndex → Prompt enriquecido
6. **Generación de respuesta** → SimpleVLLM (Qwen 2.5 14B) → Streaming
7. **Respuesta al usuario** → WebSocket → Frontend

**Persistencia**:
- Conversación guardada en PostgreSQL
- Caché actualizado en Redis
- Logs en volumen compartido

---

## Health Checks

### Liveness Probe
```yaml
httpGet:
  path: /health
  port: 8080
initialDelaySeconds: 30
periodSeconds: 10
```

### Readiness Probe
```yaml
httpGet:
  path: /health
  port: 8080
initialDelaySeconds: 10
periodSeconds: 5
```

---

## StorageClass

**Longhorn** - Sistema de almacenamiento distribuido
- Soporta ReadWriteMany para volúmenes compartidos
- Replicación de datos entre nodos
- Snapshots y backups

---

## Consideraciones de Migración

### De SQLite a PostgreSQL
Al desplegar por primera vez con PostgreSQL:
1. Open WebUI detecta `DATABASE_URL` y usa PostgreSQL automáticamente
2. Se crean tablas automáticamente en el primer inicio
3. No se migran datos de SQLite existente (se pierde historial anterior)

### Compatibilidad con Versiones Anteriores
- Si se elimina `DATABASE_URL`, Open WebUI vuelve a SQLite
- Si se elimina Redis, WebSocket funciona pero sin sincronización entre réplicas
- Sin `WEBUI_SECRET_KEY`, cada réplica genera su propia clave (sesiones inconsistentes)

---

## Troubleshooting

### Problema: Pods en CrashLoopBackOff
**Causas posibles**:
- PostgreSQL no está listo (verificar pod postgresql)
- Redis inaccesible (verificar pod redis)
- PVC no puede montarse (verificar que Longhorn soporte ReadWriteMany)

**Verificación**:
```bash
kubectl logs -n rag-system -l app=open-webui --tail=100
kubectl get pods -n rag-system  # Verificar estado de PostgreSQL y Redis
```

### Problema: Usuarios deslogueados aleatoriamente
**Causa**: Secret key diferente entre réplicas o no configurada

**Solución**:
- Verificar que secret `openwebui-secret` existe
- Confirmar que todas las réplicas usan la misma clave

### Problema: Error 403 en WebSocket
**Causa**: Redis no configurado correctamente

**Solución**:
- Verificar `WEBSOCKET_MANAGER: redis`
- Verificar conectividad a Redis Sentinel
- Revisar logs para errores de conexión Redis

### Problema: Configuraciones no se sincronizan entre réplicas
**Causa**: `REDIS_URL` no configurado

**Solución**:
- Verificar variable de entorno `REDIS_URL` (separada de `WEBSOCKET_REDIS_URL`)
- Asegurar que apunta a DB 3 de Redis

---

## Comandos Útiles

### Ver estado de pods
```bash
kubectl get pods -n rag-system
kubectl get pods -n redis-sentinel
kubectl get pods -n simplevllm
```

### Ver logs de Open WebUI
```bash
kubectl logs -n rag-system -l app=open-webui --tail=50 -f
```

### Verificar conectividad Redis
```bash
kubectl exec -n rag-system deployment/open-webui -- \
  redis-cli -h redis-service ping
```

### Verificar conectividad PostgreSQL
```bash
kubectl exec -n rag-system deployment/open-webui -- \
  nc -zv postgres 5432

# O conectarse directamente a PostgreSQL
kubectl exec -n rag-system statefulset/postgresql -- \
  psql -U ragsystemuser -d ragsystemdb -c "SELECT version();"
```

### Escalar manualmente
```bash
kubectl scale deployment open-webui -n rag-system --replicas=3
```

### Ver métricas HPA
```bash
kubectl get hpa -n rag-system
kubectl describe hpa open-webui-hpa -n rag-system
```

---

## Archivos de Configuración

| Archivo | Descripción |
|---------|-------------|
| `00-configmap.yaml` | ConfigMap con configuración de servicios |
| `01-storage.yaml` | PVCs para Open WebUI, Qdrant, LlamaIndex |
| `02-qdrant.yaml` | Deployment y Service de Qdrant |
| `03-secrets.yaml` | Secrets de Redis y Open WebUI |
| `04-openwebui.yaml` | Deployment, Service e Ingress de Open WebUI |
| `05-hpa.yaml` | HorizontalPodAutoscaler para Open WebUI |
| `06-pipeline.yaml` | Deployment de pipelines personalizados |
| `07-docling-gpu.yaml` | Servicio de procesamiento de documentos con GPU |
| `08-redis.yaml` | StatefulSet y Service de Redis |
| `09-postgresql.yaml` | StatefulSet, Service y Secrets de PostgreSQL |
| `kustomization.yaml` | Archivo principal de Kustomize |

---

## Contacto y Soporte

Para problemas o consultas sobre este despliegue:
- Namespace: `rag-system`
- Owner: Colegio de Técnicos de la Provincia de Buenos Aires
- Entorno: Producción

---

**Última actualización**: 2025-12-10
**Versión de Open WebUI**: main (latest)
**Modelo LLM**: Qwen 2.5 14B Instruct
**Modelo Embedding**: Qwen3 Embedding 0.6B
**PostgreSQL**: 16-alpine (interno)
**Redis**: 7-alpine (interno)
