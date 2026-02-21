FROM quay.io/docling-project/docling-serve:latest

USER root

# Instalar dependencias necesarias
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Instalar docling-core para acceder a los tipos de elementos
RUN pip install --no-cache-dir docling-core

# Copiar la aplicación
COPY app.py /opt/app-root/src/app.py

USER 1001

WORKDIR /opt/app-root/src

EXPOSE 5001

CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5001"]
