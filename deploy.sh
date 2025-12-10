#!/bin/bash

# Script de deployment para RAG Stack en Kubernetes
# Requisitos: kubectl configurado y acceso al cluster

set -e

echo "🚀 Desplegando RAG Stack con Reranking en Kubernetes"
echo "=================================================="

# Colores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Función para esperar por un deployment
wait_for_deployment() {
    local namespace=$1
    local deployment=$2
    echo -e "${YELLOW}⏳ Esperando a que $deployment esté listo...${NC}"
    kubectl wait --for=condition=available --timeout=300s deployment/$deployment -n $namespace
    echo -e "${GREEN}✅ $deployment listo${NC}"
}

# Función para esperar por un pod
wait_for_pod() {
    local namespace=$1
    local label=$2
    echo -e "${YELLOW}⏳ Esperando a que los pods con label $label estén listos...${NC}"
    kubectl wait --for=condition=ready --timeout=300s pod -l $label -n $namespace
    echo -e "${GREEN}✅ Pods con label $label listos${NC}"
}

echo ""
echo "📋 Paso 1: Crear namespace y configuración"
kubectl apply -f 00-namespace.yaml
echo -e "${GREEN}✅ Namespace y ConfigMap creados${NC}"

echo ""
echo "💾 Paso 2: Crear PersistentVolumeClaims"
kubectl apply -f 01-storage.yaml
echo -e "${GREEN}✅ PVCs creados${NC}"

echo ""
echo "🗄️ Paso 3: Desplegar Qdrant (Vector Database)"
kubectl apply -f 02-qdrant.yaml
wait_for_deployment rag-system qdrant

echo ""
echo "🤖 Paso 4: Desplegar LlamaIndex API con Reranking"
kubectl apply -f 03-llamaindex-configmap.yaml
kubectl apply -f 03-llamaindex-api.yaml
wait_for_deployment rag-system llamaindex-api

echo ""
echo "🌐 Paso 5: Desplegar Open WebUI"
kubectl apply -f 04-openwebui.yaml
wait_for_deployment rag-system open-webui

echo ""
echo "=================================================="
echo -e "${GREEN}✅ ¡Deployment completado exitosamente!${NC}"
echo "=================================================="
echo ""
echo "📊 Estado de los servicios:"
kubectl get pods -n rag-system
echo ""
kubectl get svc -n rag-system
echo ""
echo "🔗 URLs de acceso:"
echo "  - Open WebUI: https://asistente.test.arba.gov.ar"
echo "  - LlamaIndex API: http://llamaindex-api-service.rag-system.svc.cluster.local:8000"
echo "  - Qdrant: http://qdrant-service.rag-system.svc.cluster.local:6333"
echo ""
echo "📝 Registry configurado:"
echo "  - Registry: registry.arba.gov.ar/infraestructura"
echo "  - Imagen: llamaindex-rag-api:1.0.0"
echo "  - Pull Secret: harbor-secret"
echo ""
echo "📖 Para ver logs:"
echo "  kubectl logs -f deployment/llamaindex-api -n rag-system"
echo "  kubectl logs -f deployment/open-webui -n rag-system"
echo "  kubectl logs -f deployment/qdrant -n rag-system"
echo ""
echo "🧪 Para probar la API de LlamaIndex:"
echo "  kubectl port-forward -n rag-system svc/llamaindex-api-service 8000:8000"
echo "  curl http://localhost:8000/health"
echo ""
echo "🔍 Para acceder a Open WebUI localmente:"
echo "  kubectl port-forward -n rag-system svc/open-webui-service 8080:80"
echo "  Abrir: http://localhost:8080"
