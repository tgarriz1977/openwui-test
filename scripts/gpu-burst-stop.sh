#!/bin/bash
#
# Baja Docling GPU y termina el nodo spot.
# Después de ejecutar: costo GPU = $0.
# Uso: ./scripts/gpu-burst-stop.sh
#

set -e

CLUSTER="colegio-staging"
REGION="us-east-2"
NODEGROUP="gpu-spot"
NS="rag-system"

echo "================================================"
echo "GPU Burst STOP"
echo "================================================"
echo ""

echo "▶ Bajando Docling GPU (replicas=0)..."
kubectl scale deployment docling-gpu --replicas=0 -n "${NS}"

echo "▶ Liberando nodo GPU (desiredSize=0)..."
aws eks update-nodegroup-config \
  --cluster-name "${CLUSTER}" \
  --region "${REGION}" \
  --nodegroup-name "${NODEGROUP}" \
  --scaling-config minSize=0,maxSize=1,desiredSize=0

echo ""
echo "================================================"
echo "✅ GPU liberado. Costo: \$0"
echo "   El nodo spot se terminará en los próximos minutos."
echo "================================================"
