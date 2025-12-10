# 🔧 Troubleshooting - Build de Imagen

## Error: ResolutionImpossible (Conflictos de Dependencias)

### Solución 1: Usar Dockerfile Simple

El `Dockerfile.simple` instala dependencias sin multi-stage, lo que puede resolver conflictos:

```bash
cd docker

# Usar el Dockerfile alternativo
./build-image-alt.sh 1.0.0

# O manualmente
docker build -f Dockerfile.simple -t registry.arba.gov.ar/infraestructura/llamaindex-rag-api:1.0.0 .
```

### Solución 2: Actualizar requirements.txt

Ya está actualizado en la última versión con versiones compatibles. Si aún falla:

```bash
# Opción minimalista - solo lo esencial
cat > requirements.txt << 'EOF'
fastapi==0.115.0
uvicorn[standard]==0.30.6
llama-index-core==0.11.14
llama-index-llms-openai-like
llama-index-embeddings-openai
llama-index-vector-stores-qdrant
qdrant-client
httpx
pydantic>=2.0
python-multipart
EOF

# Rebuild
docker build -t registry.arba.gov.ar/infraestructura/llamaindex-rag-api:1.0.0 .
```

### Solución 3: Build sin cache

```bash
docker build --no-cache -t registry.arba.gov.ar/infraestructura/llamaindex-rag-api:1.0.0 .
```

### Solución 4: Usar imagen base con dependencias preinstaladas

```dockerfile
# Dockerfile.prebuilt
FROM python:3.11-slim

# Instalar solo lo necesario
RUN pip install --no-cache-dir \
    fastapi uvicorn[standard] \
    llama-index-core \
    qdrant-client httpx pydantic

# Copiar código
COPY llamaindex_service.py /app/
WORKDIR /app

CMD ["uvicorn", "llamaindex_service:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Error: FROM casing warning

✅ **Ya arreglado** en Dockerfile - cambié `as` a `AS`

## Builds muy lentos

### Optimización 1: BuildKit

```bash
# Habilitar BuildKit
export DOCKER_BUILDKIT=1
docker build -t registry.arba.gov.ar/infraestructura/llamaindex-rag-api:1.0.0 .
```

### Optimización 2: Cache de layers

```bash
# Build usando cache de versión anterior
docker build \
  --cache-from registry.arba.gov.ar/infraestructura/llamaindex-rag-api:latest \
  -t registry.arba.gov.ar/infraestructura/llamaindex-rag-api:1.0.1 .
```

## Imagen muy grande

### Ver qué ocupa espacio

```bash
docker history registry.arba.gov.ar/infraestructura/llamaindex-rag-api:1.0.0 --human
```

### Reducir tamaño

```dockerfile
# Usar alpine (más pequeño pero puede tener problemas)
FROM python:3.11-alpine

# Limpiar después de instalar
RUN pip install ... && \
    rm -rf /root/.cache/pip && \
    find /usr/local -type f -name '*.pyc' -delete
```

## Error al pushear a Harbor

### Autenticación

```bash
# Login explícito
docker login registry.arba.gov.ar
# Usuario: tu-usuario-arba
# Password: tu-token (no la contraseña normal)

# Verificar login
cat ~/.docker/config.json | grep registry.arba.gov.ar
```

### Permisos

```bash
# Verificar que tienes permisos en el proyecto 'infraestructura'
# Contactar al admin de Harbor si no tienes acceso
```

### Tamaño máximo

```bash
# Si la imagen es muy grande (>2GB), Harbor puede rechazarla
# Verificar límites del proyecto en Harbor UI

# Comprimir layers
docker build --squash -t registry.arba.gov.ar/infraestructura/llamaindex-rag-api:1.0.0 .
```

## Test local antes de pushear

```bash
# 1. Build
docker build -t llamaindex-test:local .

# 2. Run local
docker run -d -p 8000:8000 \
  -e LLM_PRIMARY_URL="http://host.docker.internal:11434" \
  -e LLM_PRIMARY_MODEL="test" \
  -e EMBEDDING_URL="http://host.docker.internal:11434" \
  -e EMBEDDING_MODEL="test" \
  -e RERANKER_URL="http://host.docker.internal:8080" \
  -e RERANKER_MODEL="test" \
  -e QDRANT_HOST="host.docker.internal" \
  --name llamaindex-test \
  llamaindex-test:local

# 3. Test
curl http://localhost:8000/health

# 4. Ver logs
docker logs llamaindex-test

# 5. Limpiar
docker stop llamaindex-test
docker rm llamaindex-test
```

## Dependencias faltantes en runtime

Si el pod inicia pero falla al importar módulos:

```bash
# Ver qué módulos están instalados
kubectl exec -it deployment/llamaindex-api -n rag-system -- pip list

# Agregar módulo faltante temporalmente
kubectl exec -it deployment/llamaindex-api -n rag-system -- \
  pip install --user nombre-del-modulo

# Luego agregarlo a requirements.txt y rebuild
```

## Build en máquina con recursos limitados

```bash
# Limitar recursos de Docker
docker build \
  --memory=2g \
  --cpu-shares=512 \
  -t registry.arba.gov.ar/infraestructura/llamaindex-rag-api:1.0.0 .

# O modificar Docker daemon
# En /etc/docker/daemon.json
{
  "default-ulimits": {
    "nofile": {
      "Hard": 64000,
      "Name": "nofile",
      "Soft": 64000
    }
  }
}
```

## Opciones de Build Recomendadas

### Build para desarrollo (rápido)

```bash
# Sin cache, sin optimizaciones
docker build -f Dockerfile.simple \
  -t llamaindex:dev .
```

### Build para staging (balanceado)

```bash
# Con cache, multi-stage
docker build \
  --cache-from registry.arba.gov.ar/infraestructura/llamaindex-rag-api:latest \
  -t registry.arba.gov.ar/infraestructura/llamaindex-rag-api:1.0.0-rc1 .
```

### Build para producción (optimizado)

```bash
# Sin cache, squash, scan
export DOCKER_BUILDKIT=1
docker build --no-cache \
  --squash \
  -t registry.arba.gov.ar/infraestructura/llamaindex-rag-api:1.0.0 .

# Escanear vulnerabilidades
docker scan registry.arba.gov.ar/infraestructura/llamaindex-rag-api:1.0.0
```

## Comandos de Diagnóstico

```bash
# Ver espacio usado por Docker
docker system df

# Limpiar imágenes antiguas
docker image prune -a

# Ver layers de la imagen
dive registry.arba.gov.ar/infraestructura/llamaindex-rag-api:1.0.0

# Inspeccionar imagen
docker inspect registry.arba.gov.ar/infraestructura/llamaindex-rag-api:1.0.0

# Test de imports
docker run --rm registry.arba.gov.ar/infraestructura/llamaindex-rag-api:1.0.0 \
  python -c "import llama_index; print('OK')"
```

## Último Recurso: Build en CI/CD

Si no puedes construir localmente, usa GitLab CI:

```yaml
# .gitlab-ci.yml
build-docker:
  stage: build
  image: docker:latest
  services:
    - docker:dind
  script:
    - docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD registry.arba.gov.ar
    - cd docker
    - docker build -t registry.arba.gov.ar/infraestructura/llamaindex-rag-api:$CI_COMMIT_SHA .
    - docker push registry.arba.gov.ar/infraestructura/llamaindex-rag-api:$CI_COMMIT_SHA
```

## FAQ

**P: ¿Puedo usar la imagen sin construirla?**
R: No hay imagen pública porque el código es específico para ARBA. Debes construirla.

**P: ¿Cuánto tarda el build?**
R: 5-10 minutos la primera vez, 2-3 minutos con cache.

**P: ¿Qué tamaño debe tener la imagen?**
R: ~400-600 MB es normal. Si es >1GB, revisar.

**P: ¿Necesito GPU para el build?**
R: No, solo CPU. GPU solo se necesita para ejecutar LLMs grandes.
