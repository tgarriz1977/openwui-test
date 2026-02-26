#!/bin/bash
#
# Levanta el nodo GPU spot y activa Docling GPU.
# Costo: ~$0.17/hr mientras el nodo está activo.
# Uso: ./scripts/gpu-burst-start.sh
#

set -e

CLUSTER="colegio-staging"
REGION="us-east-2"
NODEGROUP="gpu-spot"
NS="rag-system"

echo "================================================"
echo "GPU Burst START"
echo "Cluster: ${CLUSTER} | Node group: ${NODEGROUP}"
echo "================================================"
echo ""

echo "▶ Escalando node group GPU a 1 instancia..."
aws eks update-nodegroup-config \
  --cluster-name "${CLUSTER}" \
  --region "${REGION}" \
  --nodegroup-name "${NODEGROUP}" \
  --scaling-config minSize=0,maxSize=1,desiredSize=1

echo "⏳ Esperando que el nodo GPU esté Ready (puede tardar 3-5 min)..."
# Esperar a que aparezca al menos un nodo con el label
for i in $(seq 1 30); do
    NODE_COUNT=$(kubectl get nodes -l node-type=gpu --no-headers 2>/dev/null | grep -c Ready || true)
    if [ "${NODE_COUNT}" -ge 1 ]; then
        echo "Nodo GPU Ready."
        break
    fi
    echo "  Intento ${i}/30 — esperando nodo..."
    sleep 20
done

kubectl wait node -l node-type=gpu \
  --for=condition=Ready --timeout=60s

echo ""
echo "▶ Levantando Docling GPU (replicas=1)..."
kubectl scale deployment docling-gpu --replicas=1 -n "${NS}"
kubectl wait deployment docling-gpu -n "${NS}" \
  --for=condition=Available --timeout=300s

echo ""
echo "================================================"
echo "✅ GPU Docling listo."
echo "   Costo activo: ~\$0.17/hr (g4dn.xlarge spot)"
echo ""
echo "   Cuando termines el procesamiento OCR:"
echo "   ./scripts/gpu-burst-stop.sh"
echo "================================================"
