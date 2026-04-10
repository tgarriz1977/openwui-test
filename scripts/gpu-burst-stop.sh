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
if kubectl get deployment docling-gpu -n "${NS}" >/dev/null 2>&1; then
    kubectl scale deployment docling-gpu --replicas=0 -n "${NS}"
else
    echo "  ⚠ Deployment 'docling-gpu' no existe en ${NS} — sigo con la liberación del nodo."
fi

echo "▶ Verificando que el node group '${NODEGROUP}' exista..."
if ! aws eks describe-nodegroup \
      --cluster-name "${CLUSTER}" \
      --region "${REGION}" \
      --nodegroup-name "${NODEGROUP}" >/dev/null 2>&1; then
    echo "❌ El node group '${NODEGROUP}' no existe. Nada que liberar."
    exit 1
fi

echo "▶ Liberando nodo GPU (desiredSize=0)..."
aws eks update-nodegroup-config \
  --cluster-name "${CLUSTER}" \
  --region "${REGION}" \
  --nodegroup-name "${NODEGROUP}" \
  --scaling-config minSize=0,maxSize=1,desiredSize=0 >/dev/null

echo "⏳ Confirmando que desiredSize quedó en 0..."
DESIRED=$(aws eks describe-nodegroup \
            --cluster-name "${CLUSTER}" \
            --region "${REGION}" \
            --nodegroup-name "${NODEGROUP}" \
            --query 'nodegroup.scalingConfig.desiredSize' \
            --output text)
if [ "${DESIRED}" != "0" ]; then
    echo "❌ desiredSize=${DESIRED} (esperaba 0). Revisá manualmente."
    exit 1
fi

echo ""
echo "================================================"
echo "✅ GPU liberado. Costo: \$0"
echo "   El nodo spot se terminará en los próximos minutos."
echo "================================================"
