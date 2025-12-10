#!/bin/bash
# Script para proteger PVs existentes antes de migrar StorageClass
#
# Este script:
# 1. Lista todos los PVs del namespace rag-system
# 2. Cambia la ReclaimPolicy a Retain (protege datos)
# 3. Crea un backup YAML de cada PV
#
# Uso:
#   bash scripts/protect-existing-pvs.sh
#

set -e

NAMESPACE="rag-system"
BACKUP_DIR="./pv-backups-$(date +%Y%m%d-%H%M%S)"

echo "=========================================="
echo "Script de Protección de PVs"
echo "=========================================="
echo ""

# Crear directorio de backup
mkdir -p "$BACKUP_DIR"
echo "✓ Directorio de backup creado: $BACKUP_DIR"
echo ""

# Obtener todos los PVCs del namespace
echo "Buscando PVCs en namespace: $NAMESPACE"
PVCS=$(kubectl get pvc -n "$NAMESPACE" -o jsonpath='{.items[*].metadata.name}')

if [ -z "$PVCS" ]; then
    echo "⚠️  No se encontraron PVCs en el namespace $NAMESPACE"
    exit 0
fi

echo "✓ PVCs encontrados: $PVCS"
echo ""

# Para cada PVC, obtener el PV asociado
for PVC in $PVCS; do
    echo "----------------------------------------"
    echo "Procesando PVC: $PVC"

    # Obtener el nombre del PV
    PV=$(kubectl get pvc "$PVC" -n "$NAMESPACE" -o jsonpath='{.spec.volumeName}')

    if [ -z "$PV" ]; then
        echo "⚠️  PVC $PVC no tiene PV asociado (puede estar en estado Pending)"
        continue
    fi

    echo "  → PV asociado: $PV"

    # Obtener el StorageClass actual
    STORAGE_CLASS=$(kubectl get pv "$PV" -o jsonpath='{.spec.storageClassName}')
    echo "  → StorageClass actual: $STORAGE_CLASS"

    # Obtener la ReclaimPolicy actual
    RECLAIM_POLICY=$(kubectl get pv "$PV" -o jsonpath='{.spec.persistentVolumeReclaimPolicy}')
    echo "  → ReclaimPolicy actual: $RECLAIM_POLICY"

    # Backup del PV
    echo "  → Creando backup del PV..."
    kubectl get pv "$PV" -o yaml > "$BACKUP_DIR/${PV}.yaml"
    echo "  ✓ Backup guardado: $BACKUP_DIR/${PV}.yaml"

    # Cambiar ReclaimPolicy a Retain si no lo está
    if [ "$RECLAIM_POLICY" != "Retain" ]; then
        echo "  → Cambiando ReclaimPolicy a Retain..."
        kubectl patch pv "$PV" -p '{"spec":{"persistentVolumeReclaimPolicy":"Retain"}}'
        echo "  ✓ ReclaimPolicy cambiado a Retain"
    else
        echo "  ✓ ReclaimPolicy ya está en Retain"
    fi

    echo ""
done

echo "=========================================="
echo "✓ Proceso completado exitosamente"
echo "=========================================="
echo ""
echo "Resumen:"
echo "  - Backups guardados en: $BACKUP_DIR"
echo "  - Todos los PVs ahora tienen ReclaimPolicy: Retain"
echo ""
echo "IMPORTANTE:"
echo "  - Los PVs están protegidos y NO se borrarán al eliminar los PVCs"
echo "  - Para recuperar un PV huérfano después:"
echo "    1. kubectl patch pv <pv-name> -p '{\"spec\":{\"claimRef\":null}}'"
echo "    2. kubectl apply -f <nuevo-pvc.yaml>"
echo ""
