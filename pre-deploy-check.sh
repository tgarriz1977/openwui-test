#!/bin/bash

# Script de validación pre-deployment para ARBA
# Verifica que todos los requisitos estén cumplidos antes de desplegar

set -e

NAMESPACE="rag-system"
REGISTRY="registry.arba.gov.ar/infraestructura"
IMAGE="llamaindex-rag-api:1.0.0"
SECRET_NAME="harbor-secret"
DOMAIN="asistente.test.arba.gov.ar"

# Colores
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}🔍 Validación Pre-Deployment ARBA${NC}"
echo "======================================"
echo ""

ERRORS=0
WARNINGS=0

# Función de check
check() {
    local check_name=$1
    local command=$2
    local is_critical=${3:-true}
    
    echo -n "  Verificando $check_name... "
    
    if eval $command > /dev/null 2>&1; then
        echo -e "${GREEN}✅${NC}"
        return 0
    else
        if [ "$is_critical" = true ]; then
            echo -e "${RED}❌${NC}"
            ((ERRORS++))
        else
            echo -e "${YELLOW}⚠️${NC}"
            ((WARNINGS++))
        fi
        return 1
    fi
}

echo -e "${YELLOW}1️⃣  Verificando conectividad a Kubernetes${NC}"
check "Conexión a cluster" "kubectl cluster-info"
check "Permisos en cluster" "kubectl auth can-i create namespace"
echo ""

echo -e "${YELLOW}2️⃣  Verificando Harbor Registry${NC}"
check "Conectividad a registry" "docker pull hello-world"
echo -n "  Verificando login a Harbor... "
if docker login registry.arba.gov.ar --username test --password test 2>&1 | grep -q "unauthorized\|denied\|Unauthorized"; then
    echo -e "${YELLOW}⚠️  (Credenciales necesarias)${NC}"
    echo "    💡 Ejecuta: docker login registry.arba.gov.ar"
    ((WARNINGS++))
else
    echo -e "${GREEN}✅${NC}"
fi

echo -n "  Verificando imagen en registry... "
if docker pull ${REGISTRY}/${IMAGE} > /dev/null 2>&1; then
    echo -e "${GREEN}✅${NC}"
    IMAGEN_SIZE=$(docker images ${REGISTRY}/${IMAGE} --format "{{.Size}}")
    echo "    📦 Tamaño: $IMAGEN_SIZE"
else
    echo -e "${RED}❌${NC}"
    echo "    💡 Necesitas construir y pushear la imagen primero:"
    echo "       cd docker && ./build-image.sh"
    ((ERRORS++))
fi
echo ""

echo -e "${YELLOW}3️⃣  Verificando namespace y secrets${NC}"
if kubectl get namespace ${NAMESPACE} > /dev/null 2>&1; then
    echo -e "  Namespace ${NAMESPACE}... ${GREEN}✅ (ya existe)${NC}"
    
    # Verificar secret
    echo -n "  Verificando secret ${SECRET_NAME}... "
    if kubectl get secret ${SECRET_NAME} -n ${NAMESPACE} > /dev/null 2>&1; then
        echo -e "${GREEN}✅${NC}"
    else
        echo -e "${RED}❌${NC}"
        echo "    💡 Necesitas crear el secret:"
        echo "       kubectl create secret docker-registry ${SECRET_NAME} \\"
        echo "         --docker-server=registry.arba.gov.ar \\"
        echo "         --docker-username=TU-USUARIO \\"
        echo "         --docker-password=TU-PASSWORD \\"
        echo "         -n ${NAMESPACE}"
        ((ERRORS++))
    fi
else
    echo -e "  Namespace ${NAMESPACE}... ${YELLOW}⚠️  (se creará durante deployment)${NC}"
fi
echo ""

echo -e "${YELLOW}4️⃣  Verificando servicios backend (LLM, Embeddings, Reranker)${NC}"
check "Namespace simplevllm" "kubectl get namespace simplevllm" false
check "Service Qwen 2.5-14B" "kubectl get svc simplevllm-svc -n simplevllm" false
check "Service Qwen 3-4B" "kubectl get svc qwen3-4b-vllm-svc -n simplevllm" false

echo -n "  Verificando servicio de embeddings... "
if curl -k -s https://qwen-embedding.test.arba.gov.ar/v1/models --max-time 5 > /dev/null 2>&1; then
    echo -e "${GREEN}✅${NC}"
else
    echo -e "${YELLOW}⚠️  (puede requerir VPN o estar en mantenimiento)${NC}"
    ((WARNINGS++))
fi

echo -n "  Verificando servicio de reranker... "
if curl -k -s https://rerankbaai.test.arba.gov.ar/health --max-time 5 > /dev/null 2>&1; then
    echo -e "${GREEN}✅${NC}"
else
    echo -e "${YELLOW}⚠️  (puede requerir VPN o estar en mantenimiento)${NC}"
    ((WARNINGS++))
fi
echo ""

echo -e "${YELLOW}5️⃣  Verificando StorageClass${NC}"
STORAGE_CLASSES=$(kubectl get storageclass --no-headers 2>/dev/null | wc -l)
if [ "$STORAGE_CLASSES" -gt 0 ]; then
    echo -e "  StorageClasses disponibles... ${GREEN}✅${NC}"
    kubectl get storageclass --no-headers | awk '{print "    - " $1}'
    
    DEFAULT_SC=$(kubectl get storageclass -o jsonpath='{.items[?(@.metadata.annotations.storageclass\.kubernetes\.io/is-default-class=="true")].metadata.name}')
    if [ ! -z "$DEFAULT_SC" ]; then
        echo "    💡 Default: $DEFAULT_SC"
    else
        echo -e "    ${YELLOW}⚠️  No hay StorageClass por defecto${NC}"
        echo "       Edita 01-storage.yaml para especificar uno"
        ((WARNINGS++))
    fi
else
    echo -e "  StorageClasses disponibles... ${RED}❌${NC}"
    ((ERRORS++))
fi
echo ""

echo -e "${YELLOW}6️⃣  Verificando Ingress Controller${NC}"
check "Namespace ingress-nginx" "kubectl get namespace ingress-nginx" false
check "Ingress Controller pods" "kubectl get pods -n ingress-nginx -l app.kubernetes.io/component=controller" false
echo ""

echo -e "${YELLOW}7️⃣  Verificando Cert-Manager${NC}"
check "Namespace cert-manager" "kubectl get namespace cert-manager" false
check "Cert-Manager pods" "kubectl get pods -n cert-manager" false
check "ClusterIssuer letsencrypt-prod" "kubectl get clusterissuer letsencrypt-prod" false
echo ""

echo -e "${YELLOW}8️⃣  Verificando recursos disponibles${NC}"
echo "  Nodos del cluster:"
kubectl get nodes --no-headers 2>/dev/null | awk '{print "    - " $1 " (" $2 ")"}'

echo ""
echo "  Recursos solicitados por el stack:"
echo "    - LlamaIndex API: 2 replicas × (1Gi RAM, 500m CPU)"
echo "    - Open WebUI: 1 replica × (1Gi RAM, 500m CPU)"
echo "    - Qdrant: 1 replica × (4Gi RAM, 2 CPU)"
echo "    - Total: ~7Gi RAM, ~4 CPU"
echo ""

echo "======================================"
if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✅ Todos los checks pasaron!${NC}"
    echo ""
    echo "Listo para desplegar:"
    echo "  make deploy-custom"
    echo "  o"
    echo "  ./deploy.sh"
    exit 0
elif [ $ERRORS -eq 0 ]; then
    echo -e "${YELLOW}⚠️  ${WARNINGS} warnings encontrados${NC}"
    echo ""
    echo "Puedes continuar pero revisa los warnings arriba."
    echo ""
    echo "Para desplegar:"
    echo "  make deploy-custom"
    exit 0
else
    echo -e "${RED}❌ ${ERRORS} errores críticos encontrados${NC}"
    if [ $WARNINGS -gt 0 ]; then
        echo -e "${YELLOW}⚠️  ${WARNINGS} warnings adicionales${NC}"
    fi
    echo ""
    echo "Debes resolver los errores críticos antes de desplegar."
    echo ""
    echo "Revisa:"
    echo "  1. Imagen pusheada a Harbor: docker push ${REGISTRY}/${IMAGE}"
    echo "  2. Secret creado en namespace: kubectl get secret ${SECRET_NAME} -n ${NAMESPACE}"
    echo "  3. Conectividad a servicios backend"
    exit 1
fi
