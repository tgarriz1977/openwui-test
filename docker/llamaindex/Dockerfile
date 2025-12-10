# Dockerfile para LlamaIndex RAG API con Reranking
# Multi-stage build para imagen más pequeña

# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /build

# Instalar dependencias del sistema necesarias para compilar
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements
COPY requirements.txt .

# Instalar dependencias Python en un directorio virtual
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir --target=/install \
    -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim

# Metadata
LABEL maintainer="ARBA DevOps Team"
LABEL description="LlamaIndex RAG API with BAAI Reranker integration"
LABEL version="1.0.0"

# Variables de entorno para Python
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Instalar solo dependencias runtime necesarias
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Crear usuario no-root para seguridad
RUN useradd -m -u 1000 -s /bin/bash appuser && \
    mkdir -p /app/data /app/logs && \
    chown -R appuser:appuser /app

WORKDIR /app

# Copiar dependencias desde builder
COPY --from=builder /install /usr/local/lib/python3.11/site-packages

# Copiar código de la aplicación
COPY --chown=appuser:appuser llamaindex_service.py .

# Cambiar a usuario no-root
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Exponer puerto
EXPOSE 8000

# Comando de inicio
CMD ["python", "-u", "llamaindex_service.py"]
