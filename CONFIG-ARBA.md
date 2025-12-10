# 🏛️ Configuración Específica ARBA

## 📋 Información del Entorno

### Registry
- **URL**: `registry.arba.gov.ar/infraestructura`
- **Secret**: `harbor-secret` (ya existente en cluster)
- **Imagen completa**: `registry.arba.gov.ar/infraestructura/llamaindex-rag-api:1.0.0`

### Dominios
- **Open WebUI**: `asistente.test.arba.gov.ar`
- **Cert-Manager Issuer**: `letsencrypt-prod`

### Servicios Backend (ya desplegados)
- **LLM Principal**: `http://simplevllm-svc.simplevllm.svc.cluster.local:8000/v1`
  - Modelo: Qwen/Qwen2.5-14B-Instruct
  - Contexto: 65,536 tokens

- **LLM Secundario**: `http://qwen3-4b-vllm-svc.simplevllm.svc.cluster.local:8000/v1`
  - Modelo: Qwen/Qwen3-4B-Instruct-2507
  - Contexto: 49,000 tokens

- **Embeddings**: `https://qwen-embedding.test.arba.gov.ar/v1`
  - Modelo: Qwen/Qwen3-Embedding-0.6B
  - Max tokens: 32,768

- **Reranker**: `https://rerankbaai.test.arba.gov.ar/rerank`
  - Modelo: BAAI/bge-reranker-v2-m3
  - Max tokens: 8,192

## 🚀 Deployment para ARBA

### Pre-requisitos

✅ **Ya tienes (NO necesitas crear):**
- Secret `harbor-secret` en el namespace
- Ingress Controller (nginx)
- Cert-Manager con issuer `letsencrypt-prod`
- Servicios de LLM, Embeddings y Reranker

❓ **Necesitas verificar:**
- StorageClass por defecto del cluster
- Acceso al registry de Harbor

### 1. Build y Push de Imagen

```bash
cd k8s-rag-stack/docker

# Login a Harbor
docker login registry.arba.gov.ar
# Usuario: tu-usuario-arba
# Password: tu-token-harbor

# Build
docker build -t registry.arba.gov.ar/infraestructura/llamaindex-rag-api:1.0.0 .

# Tag latest
docker tag registry.arba.gov.ar/infraestructura/llamaindex-rag-api:1.0.0 \
           registry.arba.gov.ar/infraestructura/llamaindex-rag-api:latest

# Push
docker push registry.arba.gov.ar/infraestructura/llamaindex-rag-api:1.0.0
docker push registry.arba.gov.ar/infraestructura/llamaindex-rag-api:latest
```

**O usando el script:**
```bash
cd docker
./build-image.sh 1.0.0
```

### 2. Verificar Harbor Secret

```bash
# Verificar que el secret existe
kubectl get secret harbor-secret -n rag-system

# Si NO existe, créalo:
kubectl create secret docker-registry harbor-secret \
  --docker-server=registry.arba.gov.ar \
  --docker-username=tu-usuario \
  --docker-password=tu-password \
  --docker-email=tu-email@arba.gov.ar \
  -n rag-system
```

### 3. Ajustar StorageClass (si es necesario)

```bash
# Ver StorageClass disponibles
kubectl get storageclass

# Si tu cluster usa otro nombre (ej: longhorn, nfs-client, etc)
# Editar en 01-storage.yaml:
nano 01-storage.yaml
# Cambiar: storageClassName: TU-STORAGE-CLASS
```

### 4. Deployment

```bash
cd k8s-rag-stack

# Opción A: Usando Makefile
make deploy-custom

# Opción B: Manual
kubectl apply -f 00-namespace.yaml
kubectl apply -f 01-storage.yaml
kubectl apply -f 02-qdrant.yaml
kubectl apply -f 03-llamaindex-api-custom-image.yaml
kubectl apply -f 04-openwebui.yaml
kubectl apply -f 05-hpa.yaml

# Verificar deployment
make status
```

### 5. Verificación

```bash
# Verificar pods
kubectl get pods -n rag-system

# Debería mostrar:
# NAME                              READY   STATUS    RESTARTS   AGE
# llamaindex-api-xxx                1/1     Running   0          2m
# llamaindex-api-yyy                1/1     Running   0          2m
# open-webui-xxx                    1/1     Running   0          2m
# qdrant-xxx                        1/1     Running   0          2m

# Verificar logs
kubectl logs -f deployment/llamaindex-api -n rag-system

# Debería mostrar:
# ✅ LlamaIndex API initialized with:
#   - LLM: Qwen/Qwen2.5-14B-Instruct @ http://simplevllm-svc...
#   - Embeddings: Qwen/Qwen3-Embedding-0.6B @ https://qwen-embedding...
#   - Reranker: BAAI/bge-reranker-v2-m3 @ https://rerankbaai...

# Test de conectividad
./test-stack.sh
```

### 6. Acceder a la Aplicación

```bash
# Via Ingress (producción)
https://asistente.test.arba.gov.ar

# Via port-forward (testing/debug)
kubectl port-forward -n rag-system svc/open-webui-service 8080:80
# Abrir: http://localhost:8080
```

## 🔧 Configuración Específica

### Variables Optimizadas para ARBA

Ya están configuradas en `00-namespace.yaml`:

```yaml
# LLM Configuration
LLM_PRIMARY_URL: "http://simplevllm-svc.simplevllm.svc.cluster.local:8000/v1"
LLM_PRIMARY_MODEL: "Qwen/Qwen2.5-14B-Instruct"
LLM_PRIMARY_CONTEXT: "65536"

# Embeddings
EMBEDDING_URL: "https://qwen-embedding.test.arba.gov.ar/v1"
EMBEDDING_MODEL: "Qwen/Qwen3-Embedding-0.6B"

# Reranker
RERANKER_URL: "https://rerankbaai.test.arba.gov.ar/rerank"
RERANKER_MODEL: "BAAI/bge-reranker-v2-m3"

# RAG Settings (optimizados para Qwen)
CHUNK_SIZE: "1000"
CHUNK_OVERLAP: "200"
RAG_TOP_K: "20"
RERANK_TOP_N: "5"
```

### Ajustes Recomendados

Dependiendo del uso, puedes ajustar:

```yaml
# Para documentos técnicos largos
CHUNK_SIZE: "1500"
CHUNK_OVERLAP: "300"

# Para respuestas más precisas (más documentos = más contexto)
RAG_TOP_K: "30"
RERANK_TOP_N: "8"

# Para respuestas más rápidas (menos documentos)
RAG_TOP_K: "15"
RERANK_TOP_N: "3"
```

## 🐛 Troubleshooting ARBA

### Problema: Imagen no se puede pullear

```bash
# Verificar secret
kubectl get secret harbor-secret -n rag-system -o yaml

# Test manual de pull
docker pull registry.arba.gov.ar/infraestructura/llamaindex-rag-api:1.0.0

# Ver eventos del pod
kubectl describe pod -n rag-system -l app=llamaindex-api

# Si falla, recrear secret
kubectl delete secret harbor-secret -n rag-system
kubectl create secret docker-registry harbor-secret \
  --docker-server=registry.arba.gov.ar \
  --docker-username=TU-USUARIO \
  --docker-password=TU-PASSWORD \
  -n rag-system
```

### Problema: No puede conectarse a servicios de embeddings/reranker

```bash
# Los servicios usan HTTPS con certificados
# Verificar conectividad desde pod

kubectl exec -it deployment/llamaindex-api -n rag-system -- \
  curl -k https://qwen-embedding.test.arba.gov.ar/v1/models

kubectl exec -it deployment/llamaindex-api -n rag-system -- \
  curl -k https://rerankbaai.test.arba.gov.ar/health

# Si fallan, verificar:
# 1. DNS interno del cluster
# 2. NetworkPolicies que bloqueen tráfico
# 3. Certificados de los servicios
```

### Problema: Ingress no responde

```bash
# Verificar ingress
kubectl get ingress -n rag-system
kubectl describe ingress open-webui-ingress -n rag-system

# Verificar certificado
kubectl get certificate -n rag-system
kubectl describe certificate open-webui-tls -n rag-system

# Ver logs del ingress controller
kubectl logs -n ingress-nginx -l app.kubernetes.io/component=controller
```

### Problema: Pods en CrashLoopBackOff

```bash
# Ver logs del pod que falla
kubectl logs -n rag-system -l app=llamaindex-api --previous

# Razones comunes:
# 1. No puede conectar a Qdrant (verificar que esté running)
# 2. Formato incorrecto de URLs de servicios
# 3. Permisos de filesystem (si usa runAsNonRoot)

# Debug interactivo
kubectl run -it --rm debug --image=registry.arba.gov.ar/infraestructura/llamaindex-rag-api:1.0.0 \
  -n rag-system -- /bin/bash
```

## 📊 Monitoreo en ARBA

### Métricas Importantes

```bash
# Uso de recursos
kubectl top pod -n rag-system

# Logs en tiempo real
kubectl logs -f deployment/llamaindex-api -n rag-system | grep "✅\|❌\|ERROR"

# Eventos
kubectl get events -n rag-system --sort-by='.lastTimestamp'
```

### Alertas Recomendadas

Si tienen Prometheus/AlertManager:

```yaml
# Ejemplo de reglas
- alert: LlamaIndexAPIDown
  expr: up{job="llamaindex-api"} == 0
  for: 5m
  annotations:
    summary: "LlamaIndex API no responde"

- alert: HighRetrievalLatency
  expr: histogram_quantile(0.95, retrieval_duration_seconds) > 2
  for: 10m
  annotations:
    summary: "Latencia de retrieval alta"
```

## 🔐 Consideraciones de Seguridad ARBA

### Network Policies (Recomendadas)

```yaml
# Restringir tráfico solo a lo necesario
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: llamaindex-api-netpol
  namespace: rag-system
spec:
  podSelector:
    matchLabels:
      app: llamaindex-api
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: open-webui
    ports:
    - protocol: TCP
      port: 8000
  egress:
  - to:
    - podSelector:
        matchLabels:
          app: qdrant
  - to:
    - namespaceSelector:
        matchLabels:
          name: simplevllm
  - to:
    - podSelector: {}
    ports:
    - protocol: TCP
      port: 443  # Para embeddings y reranker HTTPS
  - to:
    - podSelector: {}
    ports:
    - protocol: TCP
      port: 53  # DNS
```

## 📝 Checklist de Deployment

```
Pre-deployment:
☐ Harbor secret existe en namespace
☐ Imagen pusheada a registry.arba.gov.ar
☐ StorageClass verificado
☐ Cert-manager funcionando

Deployment:
☐ Namespace creado
☐ PVCs creados y bound
☐ Qdrant running
☐ LlamaIndex API running (2 replicas)
☐ Open WebUI running
☐ HPA configurado

Post-deployment:
☐ Ingress responde en asistente.test.arba.gov.ar
☐ Certificado SSL válido
☐ Test de conectividad a servicios backend OK
☐ Test de ingesta de documentos OK
☐ Test de consulta con RAG OK
☐ Test de reranking funcionando
☐ Logs sin errores
☐ Métricas disponibles (si aplica)
```

## 📞 Contacto y Soporte

Para incidencias o consultas:
- Logs: `kubectl logs -f deployment/llamaindex-api -n rag-system`
- Status: `kubectl get all -n rag-system`
- Describe: `kubectl describe pod -n rag-system -l app=llamaindex-api`

---

**Configurado para**: ARBA
**Registry**: registry.arba.gov.ar/infraestructura
**Dominio**: asistente.test.arba.gov.ar
**Versión**: 1.0.0
