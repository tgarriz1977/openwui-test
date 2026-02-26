# Docling GPU — OCR bajo demanda

Docling corre con GPU (NVIDIA T4) en un nodo spot que se levanta solo cuando hay procesamiento OCR masivo y se termina al finalizar. Costo en reposo: **$0**.

## Cómo funciona

```
Reposo:    docling-gpu replicas=0  →  sin nodo GPU  →  $0/hr
           (uploads en OpenWebUI fallan con error de conexión)

Burst:     docling-gpu replicas=1  →  g4dn.xlarge spot  →  ~$0.17/hr
           (OCR funcionando, 5-10x más rápido que CPU)
```

El Service `docling` en Kubernetes siempre existe — OpenWebUI apunta a él. Cuando el deployment está en 0 réplicas simplemente no hay pods detrás y los uploads fallan. Cuando se escala a 1, el Service empieza a rutear al pod GPU automáticamente.

## Uso diario

```bash
# Antes de procesar documentos
./scripts/gpu-burst-start.sh

# ... subir y procesar PDFs en OpenWebUI ...

# Al terminar
./scripts/gpu-burst-stop.sh
```

`gpu-burst-start.sh` tarda ~5 minutos (el nodo spot tarda en unirse al cluster).

## Costo estimado

| Escenario | Tiempo activo | Costo |
|---|---|---|
| 50 PDFs | ~30 min | ~$0.09 |
| 200 PDFs | ~1.5 hrs | ~$0.26 |
| 500 PDFs | ~3 hrs | ~$0.51 |

*g4dn.xlarge spot en us-east-2, precio orientativo ~$0.17/hr*

---

## Setup inicial (una sola vez)

Estos pasos se hacen una única vez para habilitar la infraestructura GPU.

### 1. Crear el node group GPU en EKS

```bash
eksctl create nodegroup \
  --cluster colegio-staging \
  --region us-east-2 \
  --name gpu-spot \
  --node-type g4dn.xlarge \
  --nodes-min 0 \
  --nodes-max 1 \
  --nodes 0 \
  --spot \
  --node-labels "node-type=gpu" \
  --node-taints "role=gpu:NoSchedule" \
  --asg-access \
  --managed
```

Usar la AMI **EKS-optimized GPU** (Amazon Linux 2). Esta AMI incluye los drivers NVIDIA a nivel del sistema operativo del nodo.

### 2. Instalar el NVIDIA Device Plugin

```bash
kubectl apply -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.17.0/deployments/static/nvidia-device-plugin.yml
```

**Por qué ambos pasos:** la AMI instala los drivers NVIDIA en el sistema operativo del nodo (para que el nodo pueda usar la GPU físicamente). El Device Plugin es un DaemonSet de Kubernetes separado que le informa al scheduler de K8s que ese nodo tiene GPUs disponibles y permite que los pods pidan `nvidia.com/gpu: 1`. Sin el Device Plugin, Kubernetes no sabe que hay GPUs aunque el nodo las tenga.

### 3. Build y push de la imagen GPU a ECR

```bash
cd docker/docling-gpu
./build-and-push.sh
```

Esto construye la imagen basada en `docling-serve-cu126` con CUDA 12.6 + `onnxruntime-gpu` y la pushea a:
```
982170164096.dkr.ecr.us-east-2.amazonaws.com/docling-serve-gpu:latest
```

### 4. Aplicar los manifiestos

```bash
# Desde la raíz del repo
kubectl apply -k .
```

O dejar que ArgoCD sincronice automáticamente. El deployment `docling-gpu` quedará en `replicas: 0`.

---

## Verificación

```bash
# Confirmar que docling-gpu está en 0 réplicas (reposo normal)
kubectl get deployment docling-gpu -n rag-system

# Con GPU activo: ver el pod corriendo
kubectl get pods -n rag-system -l variant=gpu

# Verificar que el nodo expone GPU
kubectl describe node -l node-type=gpu | grep nvidia.com/gpu

# Health check de Docling (con gpu-burst-start.sh activo)
kubectl port-forward -n rag-system deployment/docling-gpu 5001:5001
curl http://localhost:5001/health
# Esperado: {"status": "ok"}

# Ver estado del node group
aws eks describe-nodegroup \
  --cluster-name colegio-staging \
  --nodegroup-name gpu-spot \
  --region us-east-2 \
  --query 'nodegroup.scalingConfig'
```

---

## Rebuild de la imagen (cuando cambia el código)

```bash
cd docker/docling-gpu
./build-and-push.sh

# Forzar que el pod use la nueva imagen
kubectl rollout restart deployment/docling-gpu -n rag-system
```

El deployment tiene `imagePullPolicy: Always`, así que al reiniciar siempre descarga la última imagen de ECR.
