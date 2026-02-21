# Dockerfile para Docling con extracción mejorada de tablas
# Basado en quay.io/docling-project/docling-serve con pdfplumber agregado

FROM quay.io/docling-project/docling-serve:latest

# Instalar dependencias Python adicionales (sin apt-get, la base no lo tiene)
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copiar la aplicación mejorada
COPY app.py /app/app.py

# Puerto por defecto de docling-serve
EXPOSE 5001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:5001/health')" || exit 1

# Comando de inicio (igual que el original)
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5001"]
