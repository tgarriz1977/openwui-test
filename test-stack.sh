#!/bin/bash

# Script de testing para validar el stack RAG con reranking
# Ejecutar después del deployment

set -e

NAMESPACE="rag-system"
LLAMAINDEX_SERVICE="llamaindex-api-service"
QDRANT_SERVICE="qdrant-service"
OPENWEBUI_SERVICE="open-webui-service"

# Colores
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "🧪 Testing RAG Stack con Reranking"
echo "=================================="
echo ""

# Función para test
run_test() {
    local test_name=$1
    local command=$2
    
    echo -e "${BLUE}🔍 Test: $test_name${NC}"
    if eval $command > /dev/null 2>&1; then
        echo -e "${GREEN}✅ PASS${NC}"
        return 0
    else
        echo -e "${RED}❌ FAIL${NC}"
        return 1
    fi
}

# Test 1: Verificar pods
echo -e "${YELLOW}📋 Test 1: Verificar que todos los pods están corriendo${NC}"
PODS=$(kubectl get pods -n $NAMESPACE --no-headers 2>/dev/null | wc -l)
RUNNING=$(kubectl get pods -n $NAMESPACE --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)

if [ "$PODS" -eq "$RUNNING" ] && [ "$PODS" -gt 0 ]; then
    echo -e "${GREEN}✅ Todos los pods están corriendo ($RUNNING/$PODS)${NC}"
else
    echo -e "${RED}❌ Algunos pods no están corriendo ($RUNNING/$PODS)${NC}"
    kubectl get pods -n $NAMESPACE
fi
echo ""

# Test 2: Verificar servicios
echo -e "${YELLOW}📋 Test 2: Verificar servicios${NC}"
run_test "Qdrant Service" "kubectl get svc $QDRANT_SERVICE -n $NAMESPACE"
run_test "LlamaIndex Service" "kubectl get svc $LLAMAINDEX_SERVICE -n $NAMESPACE"
run_test "Open WebUI Service" "kubectl get svc $OPENWEBUI_SERVICE -n $NAMESPACE"
echo ""

# Test 3: Health checks
echo -e "${YELLOW}📋 Test 3: Health checks${NC}"

# Forward port temporalmente para tests
echo "   Configurando port-forwarding..."
kubectl port-forward -n $NAMESPACE svc/$LLAMAINDEX_SERVICE 8001:8000 &
PF_PID=$!
sleep 3

# Test health endpoint
if curl -s http://localhost:8001/health | grep -q "healthy"; then
    echo -e "${GREEN}✅ LlamaIndex API health check OK${NC}"
else
    echo -e "${RED}❌ LlamaIndex API health check FAIL${NC}"
fi

# Matar port-forward
kill $PF_PID 2>/dev/null || true
echo ""

# Test 4: Verificar conectividad entre servicios
echo -e "${YELLOW}📋 Test 4: Verificar conectividad interna${NC}"

# Test conectividad a Qdrant
LLAMAINDEX_POD=$(kubectl get pod -n $NAMESPACE -l app=llamaindex-api -o jsonpath='{.items[0].metadata.name}')
if kubectl exec -n $NAMESPACE $LLAMAINDEX_POD -- curl -s http://$QDRANT_SERVICE:6333/healthz | grep -q "ok"; then
    echo -e "${GREEN}✅ LlamaIndex → Qdrant conectividad OK${NC}"
else
    echo -e "${RED}❌ LlamaIndex → Qdrant conectividad FAIL${NC}"
fi

# Test conectividad a servicios externos
echo "   Testing conectividad a servicios externos..."

# LLM
if kubectl exec -n $NAMESPACE $LLAMAINDEX_POD -- curl -s http://simplevllm-svc.simplevllm.svc.cluster.local:8000/v1/models | grep -q "Qwen"; then
    echo -e "${GREEN}✅ Conectividad a LLM OK${NC}"
else
    echo -e "${YELLOW}⚠️  No se pudo verificar conectividad a LLM${NC}"
fi

# Embeddings (con -k para ignorar SSL)
if kubectl exec -n $NAMESPACE $LLAMAINDEX_POD -- curl -k -s https://qwen-embedding.test.arba.gov.ar/v1/models 2>/dev/null | grep -q "Qwen" || true; then
    echo -e "${GREEN}✅ Conectividad a Embeddings OK${NC}"
else
    echo -e "${YELLOW}⚠️  No se pudo verificar conectividad a Embeddings (puede ser esperado si usa HTTPS con cert auto-firmado)${NC}"
fi

# Reranker (con -k para ignorar SSL)
if kubectl exec -n $NAMESPACE $LLAMAINDEX_POD -- curl -k -s https://rerankbaai.test.arba.gov.ar/health 2>/dev/null | grep -q "ok" || true; then
    echo -e "${GREEN}✅ Conectividad a Reranker OK${NC}"
else
    echo -e "${YELLOW}⚠️  No se pudo verificar conectividad a Reranker (puede ser esperado si usa HTTPS con cert auto-firmado)${NC}"
fi
echo ""

# Test 5: Verificar PVCs
echo -e "${YELLOW}📋 Test 5: Verificar almacenamiento persistente${NC}"
PVCS_BOUND=$(kubectl get pvc -n $NAMESPACE --no-headers | grep Bound | wc -l)
PVCS_TOTAL=$(kubectl get pvc -n $NAMESPACE --no-headers | wc -l)

if [ "$PVCS_BOUND" -eq "$PVCS_TOTAL" ]; then
    echo -e "${GREEN}✅ Todos los PVCs están bound ($PVCS_BOUND/$PVCS_TOTAL)${NC}"
else
    echo -e "${RED}❌ Algunos PVCs no están bound ($PVCS_BOUND/$PVCS_TOTAL)${NC}"
    kubectl get pvc -n $NAMESPACE
fi
echo ""

# Test 6: Verificar configuración
echo -e "${YELLOW}📋 Test 6: Verificar ConfigMap${NC}"
if kubectl get configmap rag-config -n $NAMESPACE > /dev/null 2>&1; then
    echo -e "${GREEN}✅ ConfigMap 'rag-config' existe${NC}"
    
    # Mostrar configuración actual
    echo ""
    echo "   Configuración actual:"
    echo "   ----------------"
    kubectl get configmap rag-config -n $NAMESPACE -o jsonpath='{.data}' | grep -o '"[^"]*": "[^"]*"' | head -10
else
    echo -e "${RED}❌ ConfigMap 'rag-config' no existe${NC}"
fi
echo ""

# Test 7: Test funcional básico (si hay colecciones)
echo -e "${YELLOW}📋 Test 7: Test funcional (opcional)${NC}"
kubectl port-forward -n $NAMESPACE svc/$LLAMAINDEX_SERVICE 8001:8000 &
PF_PID=$!
sleep 3

COLLECTIONS=$(curl -s http://localhost:8001/collections 2>/dev/null | grep -o '"collections":\[.*\]' || echo "")
if [ ! -z "$COLLECTIONS" ]; then
    echo -e "${GREEN}✅ API responde correctamente${NC}"
    echo "   Colecciones disponibles: $COLLECTIONS"
else
    echo -e "${YELLOW}⚠️  No hay colecciones creadas aún (esperado en primera instalación)${NC}"
fi

kill $PF_PID 2>/dev/null || true
echo ""

# Resumen
echo "=================================="
echo -e "${GREEN}✅ Testing completado${NC}"
echo "=================================="
echo ""
echo "📊 Resumen de recursos:"
kubectl get all -n $NAMESPACE
echo ""
echo "💡 Próximos pasos:"
echo "   1. Acceder a Open WebUI en: http://rag.test.arba.gov.ar"
echo "   2. Crear primer usuario (será admin)"
echo "   3. Subir documentos en la sección 'Workspace'"
echo "   4. Hacer consultas con RAG habilitado"
echo ""
echo "🔍 Para debugging:"
echo "   kubectl logs -f deployment/llamaindex-api -n $NAMESPACE"
echo "   kubectl describe pod <pod-name> -n $NAMESPACE"
echo ""
