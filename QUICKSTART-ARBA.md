# 🚀 Quick Start - ARBA

## Deployment en 5 Pasos

### 📋 Pre-requisito
Tener acceso al cluster de Kubernetes de ARBA y credenciales de Harbor.

---

### 1️⃣ Build y Push de Imagen (5 min)

```bash
# Descomprimir
tar -xzf k8s-rag-stack-final.tar.gz
cd k8s-rag-stack

# Login a Harbor
docker login registry.arba.gov.ar
# Usuario: tu-usuario-arba
# Password: tu-token-harbor

# Build y push
cd docker
./build-image.sh 1.0.0

# Verificar que la imagen está en Harbor
docker pull registry.arba.gov.ar/infraestructura/llamaindex-rag-api:1.0.0
```

✅ **Resultado esperado**: Imagen en Harbor (~400MB)

---

### 2️⃣ Verificar Secret de Harbor (1 min)

```bash
cd ..

# Verificar si el secret ya existe
kubectl get secret harbor-secret -n rag-system

# Si NO existe, créalo:
kubectl create namespace rag-system
kubectl create secret docker-registry harbor-secret \
  --docker-server=registry.arba.gov.ar \
  --docker-username=TU-USUARIO \
  --docker-password=TU-PASSWORD \
  --docker-email=tu-email@arba.gov.ar \
  -n rag-system
```

✅ **Resultado esperado**: Secret creado o ya existente

---

### 3️⃣ Validar Pre-requisitos (2 min)

```bash
# Ejecutar script de validación
./pre-deploy-check.sh

# O con Makefile
make pre-check
```

✅ **Resultado esperado**: Todos los checks en verde (✅)

Si hay errores rojos (❌), resolver antes de continuar.

---

### 4️⃣ Desplegar Stack (3 min)

```bash
# Opción A: Makefile (recomendado)
make deploy-custom

# Opción B: Script
./deploy.sh

# Opción C: Manual
kubectl apply -f 00-namespace.yaml
kubectl apply -f 01-storage.yaml
kubectl apply -f 02-qdrant.yaml
kubectl apply -f 03-llamaindex-api-custom-image.yaml
kubectl apply -f 04-openwebui.yaml
kubectl apply -f 05-hpa.yaml
```

✅ **Resultado esperado**: Todos los pods en estado Running

---

### 5️⃣ Verificar y Acceder (2 min)

```bash
# Ver estado
make status

# O manualmente
kubectl get pods -n rag-system

# Deberías ver:
# llamaindex-api-xxx    1/1  Running
# llamaindex-api-yyy    1/1  Running
# open-webui-xxx        1/1  Running
# qdrant-xxx            1/1  Running

# Acceder a la aplicación
# Navegador: https://asistente.test.arba.gov.ar

# O port-forward para testing
make port-forward-webui
# Navegador: http://localhost:8080
```

✅ **Resultado esperado**: Interfaz de Open WebUI funcionando

---

## 🎉 ¡Listo!

Ahora puedes:

### 1. Crear Usuario Admin
- Primera persona en registrarse = Admin
- Ir a https://asistente.test.arba.gov.ar
- Click en "Sign up"
- Completar datos

### 2. Subir Documentos
- Click en "Workspace" o ícono de carpeta
- "Add Documents" o "Upload"
- Arrastrar archivos PDF, DOCX, TXT
- Esperar a que se procesen

### 3. Hacer Consultas con RAG
- Crear nuevo chat
- Click en "#" para seleccionar colección
- Escribir pregunta
- Ver respuesta con fuentes

---

## 🐛 Problemas Comunes

### ❌ Pods en ImagePullBackOff
```bash
# Verificar secret
kubectl describe pod -n rag-system -l app=llamaindex-api | grep -A5 Events

# Solución: Recrear secret con credenciales correctas
kubectl delete secret harbor-secret -n rag-system
kubectl create secret docker-registry harbor-secret \
  --docker-server=registry.arba.gov.ar \
  --docker-username=TU-USUARIO \
  --docker-password=TU-PASSWORD \
  -n rag-system

kubectl rollout restart deployment/llamaindex-api -n rag-system
```

### ❌ Pods en CrashLoopBackOff
```bash
# Ver logs
kubectl logs -n rag-system -l app=llamaindex-api

# Causas comunes:
# 1. Qdrant no está corriendo
kubectl get pods -n rag-system -l app=qdrant

# 2. No puede conectar a servicios backend
kubectl exec -n rag-system deployment/llamaindex-api -- \
  curl http://simplevllm-svc.simplevllm.svc.cluster.local:8000/v1/models
```

### ❌ Ingress no responde
```bash
# Verificar ingress
kubectl get ingress -n rag-system
kubectl describe ingress open-webui-ingress -n rag-system

# Verificar que el dominio apunta al cluster
nslookup asistente.test.arba.gov.ar

# Verificar certificado SSL
kubectl get certificate -n rag-system
```

### ❌ PVCs en Pending
```bash
# Ver qué StorageClass está usando
kubectl get pvc -n rag-system

# Si no hay default StorageClass, editarlo
nano 01-storage.yaml
# Cambiar: storageClassName: TU-STORAGE-CLASS
kubectl apply -f 01-storage.yaml
```

---

## 📊 Comandos Útiles

```bash
# Ver todo el estado
make status

# Ver logs en tiempo real
make logs

# Reiniciar servicios
make restart-api
make restart-webui

# Escalar
make scale-api REPLICAS=3

# Port-forward para debugging
make port-forward-api    # Puerto 8000
make port-forward-webui  # Puerto 8080

# Ver uso de recursos
kubectl top pods -n rag-system

# Eliminar todo (CUIDADO: borra datos)
make delete-all
```

---

## 📞 Soporte

Si algo falla:

1. **Revisar logs**:
   ```bash
   make logs
   ```

2. **Ejecutar tests**:
   ```bash
   ./test-stack.sh
   ```

3. **Ver eventos**:
   ```bash
   kubectl get events -n rag-system --sort-by='.lastTimestamp'
   ```

4. **Consultar documentación**:
   - `README.md` - Documentación completa
   - `CONFIG-ARBA.md` - Configuración específica ARBA
   - `DOCKER-GUIDE.md` - Guía de Docker

---

## ✅ Checklist de Deployment

```
Pre-deployment:
☐ Docker instalado y acceso a registry.arba.gov.ar
☐ kubectl configurado con acceso al cluster
☐ Credenciales de Harbor

Build & Push:
☐ Imagen construida localmente
☐ Imagen pusheada a Harbor
☐ Tag latest también pusheado

Kubernetes:
☐ harbor-secret creado en namespace rag-system
☐ Pre-check ejecutado sin errores críticos
☐ Stack desplegado

Verificación:
☐ Todos los pods Running
☐ Ingress responde en asistente.test.arba.gov.ar
☐ Certificado SSL válido
☐ Usuario admin creado
☐ Documentos de prueba subidos
☐ Consulta de prueba con RAG funciona
```

---

**Tiempo total estimado**: ~15 minutos

**¿Preguntas?** Ver `CONFIG-ARBA.md` para troubleshooting detallado.
