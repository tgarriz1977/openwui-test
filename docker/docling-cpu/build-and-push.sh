#!/bin/bash
#
# Script de build y push de la imagen mejorada de Docling
#

set -e

# Configuración
AWS_ACCOUNT="982170164096"
AWS_REGION="us-east-2"
ECR_REPO="docling-serve-enhanced"
IMAGE_TAG="latest"
LOCAL_TAG="docling-serve-enhanced:${IMAGE_TAG}"
FULL_TAG="${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:${IMAGE_TAG}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "================================================"
echo "🐳 Build de Docling Serve Mejorado"
echo "================================================"
echo ""

# Verificar Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker no está instalado${NC}"
    exit 1
fi

# Verificar AWS CLI
if ! command -v aws &> /dev/null; then
    echo -e "${RED}❌ AWS CLI no está instalado${NC}"
    exit 1
fi

echo -e "${BLUE}🔍 Configuración:${NC}"
echo "   Región: ${AWS_REGION}"
echo "   Repositorio: ${ECR_REPO}"
echo "   Tag: ${IMAGE_TAG}"
echo ""

# Login a ECR
echo -e "${BLUE}🔐 Login a AWS ECR...${NC}"
aws ecr get-login-password --region ${AWS_REGION} | \
    docker login --username AWS --password-stdin ${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com

echo -e "${GREEN}✅ Login exitoso${NC}"
echo ""

# Build
echo -e "${BLUE}🏗️  Building imagen...${NC}"
docker build -t ${LOCAL_TAG} .

echo -e "${GREEN}✅ Build completado${NC}"
echo ""

# Tag
echo -e "${BLUE}🏷️  Tagging imagen...${NC}"
docker tag ${LOCAL_TAG} ${FULL_TAG}

echo -e "${GREEN}✅ Tag aplicado: ${FULL_TAG}${NC}"
echo ""

# Push
echo -e "${BLUE}📤 Push a ECR...${NC}"
docker push ${FULL_TAG}

echo -e "${GREEN}✅ Push completado${NC}"
echo ""

# Verificar
echo -e "${BLUE}🔍 Verificando imagen en ECR...${NC}"
aws ecr describe-images --region ${AWS_REGION} \
    --repository-name ${ECR_REPO} \
    --image-ids imageTag=${IMAGE_TAG} \
    --query 'imageDetails[0].{Size:imageSizeInBytes,Tag:imageTags[0],Digest:imageDigest}' \
    --output table

echo ""
echo "================================================"
echo -e "${GREEN}✅ Proceso completado exitosamente!${NC}"
echo "================================================"
echo ""
echo "Imagen: ${FULL_TAG}"
echo ""
echo "Próximos pasos:"
echo "1. Actualizar 07-docling.yaml con la nueva imagen"
echo "2. kubectl apply -f 07-docling.yaml"
echo "3. ArgoCD sincronizará automáticamente"
echo ""
echo "Para probar localmente:"
echo "  docker run -p 5001:5001 ${FULL_TAG}"
