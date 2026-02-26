#!/bin/bash
#
# Build y push de la imagen Docling GPU a ECR
#

set -e

AWS_ACCOUNT="982170164096"
AWS_REGION="us-east-2"
ECR_REPO="docling-serve-gpu"
IMAGE_TAG="latest"
LOCAL_TAG="docling-serve-gpu:${IMAGE_TAG}"
FULL_TAG="${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:${IMAGE_TAG}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "================================================"
echo "Build de Docling Serve GPU (CUDA 12.6)"
echo "================================================"
echo ""

if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker no instalado"
    exit 1
fi

if ! command -v aws &> /dev/null; then
    echo "ERROR: AWS CLI no instalado"
    exit 1
fi

echo "Configuracion:"
echo "  Region:      ${AWS_REGION}"
echo "  Repositorio: ${ECR_REPO}"
echo "  Tag:         ${IMAGE_TAG}"
echo ""

echo "Login a AWS ECR..."
aws ecr get-login-password --region ${AWS_REGION} | \
    docker login --username AWS --password-stdin ${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com
echo "Login OK"
echo ""

echo "Creando repositorio ECR si no existe..."
aws ecr describe-repositories --region ${AWS_REGION} --repository-names ${ECR_REPO} &>/dev/null || \
    aws ecr create-repository --region ${AWS_REGION} --repository-name ${ECR_REPO}
echo ""

echo "Building imagen GPU..."
docker build -t ${LOCAL_TAG} "${SCRIPT_DIR}"
echo "Build OK"
echo ""

echo "Tagging..."
docker tag ${LOCAL_TAG} ${FULL_TAG}
echo ""

echo "Push a ECR..."
docker push ${FULL_TAG}
echo ""

echo "================================================"
echo "Completado: ${FULL_TAG}"
echo "================================================"
echo ""
echo "Proximos pasos:"
echo "1. Asegurarse de que el node group 'gpu-spot' existe en EKS"
echo "2. Para procesar OCR: ./scripts/gpu-burst-start.sh"
echo ""
