# 🚀 RAG Stack con Reranking para Kubernetes

Stack completo de RAG (Retrieval-Augmented Generation) optimizado para Kubernetes, utilizando tus servicios de LLM, Embeddings y Reranker existentes.

## 📋 Arquitectura

```
┌─────────────────┐
│   Open WebUI    │  ← Frontend (Usuario)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ LlamaIndex API  │  ← Orquestación RAG + Reranking
└────┬───┬───┬────┘
     │   │   │
     │   │   └──────────────┐
     │   │                  │
     ▼   ▼                  ▼
┌────────┐  ┌──────────┐  ┌─────────────┐
│ Qdrant │  │  Qwen    │  │BAAI Reranker│
│Vector  │  │LLM+Embed │  │   (BGE)     │
│   DB   │  │          │  │             │
└────────┘  └──────────┘  └─────────────┘
```

## 🎯 Componentes

### 1. **Qdrant** (Vector Database)
- Almacenamiento de embeddings
- Búsqueda vectorial rápida
- Persistencia de colecciones

### 2. **LlamaIndex API** (Motor RAG)
- Chunking inteligente de documentos
- Recuperación con Top-K configurable
- Reranking automático con BAAI/bge-reranker-v2-m3
- API REST para ingesta y consultas

### 3. **Open WebUI** (Frontend)
- Interfaz de chat intuitiva
- Gestión de documentos
- Múltiples colecciones
- Configuración de parámetros RAG

### 4. **Servicios Externos** (Ya desplegados)
- **LLM**: Qwen2.5-14B-Instruct (65K contexto)
- **LLM Small**: Qwen3-4B-Instruct (49K contexto)
- **Embeddings**: Qwen3-Embedding-0.6B (32K tokens)
- **Reranker**: BAAI/bge-reranker-v2-m3 (8K tokens)

## 🔧 Requisitos

- Kubernetes 1.24+
- kubectl configurado
- StorageClass disponible
- Ingress Controller (nginx recomendado)
- Cert-Manager (opcional, para TLS)

## 🚀 Deployment

### Opción 1: Deployment Automático

```bash
cd k8s-rag-stack
chmod +x deploy.sh
./deploy.sh
```

### Opción 2: Deployment Manual

```bash
# 1. Crear namespace y configuración
kubectl apply -f 00-namespace.yaml

# 2. Crear volúmenes persistentes
kubectl apply -f 01-storage.yaml

# 3. Desplegar Qdrant
kubectl apply -f 02-qdrant.yaml

# 4. Desplegar LlamaIndex API
kubectl apply -f 03-llamaindex-configmap.yaml
kubectl apply -f 03-llamaindex-api.yaml

# 5. Desplegar Open WebUI
kubectl apply -f 04-openwebui.yaml

# 6. Verificar deployment
kubectl get pods -n rag-system
kubectl get svc -n rag-system
```

## ⚙️ Configuración

### Variables de Entorno Principales

Editar `00-namespace.yaml` para ajustar:

```yaml
# RAG Settings
CHUNK_SIZE: "1000"          # Tamaño de chunks
CHUNK_OVERLAP: "200"        # Superposición entre chunks
RAG_TOP_K: "20"            # Documentos recuperados antes de reranking
RERANK_TOP_N: "5"          # Documentos finales después de reranking
```

### Ajustar Recursos

Editar los archivos de deployment para modificar:

```yaml
resources:
  requests:
    memory: "2Gi"
    cpu: "1"
  limits:
    memory: "4Gi"
    cpu: "2"
```

## 📊 Uso

### Acceder a Open WebUI

1. **Vía Ingress** (producción):
   ```
   https://rag.test.arba.gov.ar
   ```

2. **Vía Port-Forward** (desarrollo):
   ```bash
   kubectl port-forward -n rag-system svc/open-webui-service 8080:80
   # Abrir: http://localhost:8080
   ```

### Usar la API de LlamaIndex

#### Health Check
```bash
kubectl port-forward -n rag-system svc/llamaindex-api-service 8000:8000

curl http://localhost:8000/health
```

#### Ingerir Documentos
```bash
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "/path/to/documents",
    "collection": "my-docs"
  }'
```

#### Consultar con Reranking
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "¿Cuál es el proceso de facturación?",
    "collection": "my-docs",
    "use_reranker": true,
    "top_k": 20,
    "rerank_top_n": 5
  }'
```

#### Listar Colecciones
```bash
curl http://localhost:8000/collections
```

## 🔍 Monitoreo

### Ver Logs

```bash
# LlamaIndex API
kubectl logs -f deployment/llamaindex-api -n rag-system

# Open WebUI
kubectl logs -f deployment/open-webui -n rag-system

# Qdrant
kubectl logs -f deployment/qdrant -n rag-system
```

### Verificar Estado

```bash
# Pods
kubectl get pods -n rag-system -w

# Servicios
kubectl get svc -n rag-system

# PVCs
kubectl get pvc -n rag-system

# Ingress
kubectl get ingress -n rag-system
```

## 🎛️ Parámetros de RAG Explicados

### Chunking
- **CHUNK_SIZE (1000)**: Tamaño de cada fragmento de texto. Valores más altos = más contexto pero menos precisión.
- **CHUNK_OVERLAP (200)**: Superposición entre chunks para mantener continuidad semántica.

### Retrieval
- **RAG_TOP_K (20)**: Número de documentos a recuperar inicialmente de Qdrant. Más documentos = más cobertura pero más ruido.

### Reranking
- **RERANK_TOP_N (5)**: Documentos finales después del reranking. El reranker selecciona los más relevantes de los TOP_K.

### Flujo Completo
```
Consulta → Qdrant (recupera 20 docs) → Reranker (selecciona top 5) → LLM (genera respuesta)
```

## 🔐 Seguridad

### Certificados TLS

Para producción, configurar cert-manager:

```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: open-webui-tls
  namespace: rag-system
spec:
  secretName: open-webui-tls
  issuerRef:
    name: letsencrypt-prod
    kind: ClusterIssuer
  dnsNames:
  - rag.test.arba.gov.ar
```

### Autenticación

Open WebUI tiene autenticación integrada. Primer usuario en registrarse se convierte en admin.

## 📈 Escalabilidad

### Escalar LlamaIndex API

```bash
kubectl scale deployment llamaindex-api -n rag-system --replicas=3
```

### Escalar Qdrant

Para alta disponibilidad, considerar desplegar Qdrant en modo cluster.

## 🐛 Troubleshooting

### LlamaIndex API no inicia

```bash
# Ver logs detallados
kubectl logs deployment/llamaindex-api -n rag-system

# Verificar conectividad a servicios
kubectl exec -it deployment/llamaindex-api -n rag-system -- curl http://qdrant-service:6333/healthz
```

### Open WebUI no conecta a Qdrant

```bash
# Verificar service
kubectl get svc qdrant-service -n rag-system

# Test de conectividad
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -n rag-system -- curl http://qdrant-service:6333/healthz
```

### Embeddings fallan

Verificar que el servicio de embeddings esté accesible:
```bash
kubectl exec -it deployment/llamaindex-api -n rag-system -- curl -k https://qwen-embedding.test.arba.gov.ar/v1/models
```

### Reranker no responde

```bash
kubectl exec -it deployment/llamaindex-api -n rag-system -- curl -k https://rerankbaai.test.arba.gov.ar/health
```

## 🔄 Actualizaciones

### Actualizar configuración

```bash
kubectl apply -f 00-namespace.yaml
kubectl rollout restart deployment/llamaindex-api -n rag-system
kubectl rollout restart deployment/open-webui -n rag-system
```

### Actualizar imágenes

```bash
kubectl set image deployment/open-webui open-webui=ghcr.io/open-webui/open-webui:latest -n rag-system
```

## 🗑️ Limpieza

```bash
# Eliminar todo el stack
kubectl delete namespace rag-system

# Solo eliminar deployments (mantener datos)
kubectl delete -f 04-openwebui.yaml
kubectl delete -f 03-llamaindex-api.yaml
kubectl delete -f 02-qdrant.yaml
```

## 📚 Recursos Adicionales

- [LlamaIndex Documentation](https://docs.llamaindex.ai/)
- [Qdrant Documentation](https://qdrant.tech/documentation/)
- [Open WebUI Documentation](https://docs.openwebui.com/)

## 🤝 Soporte

Para issues o preguntas, contactar al equipo de infraestructura.

## 📝 Notas

- **Reranking**: El uso de BAAI/bge-reranker-v2-m3 mejora significativamente la relevancia de los resultados comparado con solo búsqueda vectorial.
- **Context Window**: El LLM Qwen2.5-14B soporta 65K tokens, permitiendo contextos muy largos.
- **Performance**: Con reranking, el flujo es: recuperar 20 docs (~2-3s) → reranking (~0.5-1s) → generación LLM (~3-10s según longitud).
# openwui-test
