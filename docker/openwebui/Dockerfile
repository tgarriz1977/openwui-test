# ---- build stage ----
FROM ghcr.io/open-webui/open-webui:main as base

USER root
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        jbig2dec \
        tesseract-ocr \
        tesseract-ocr-spa \
        tesseract-ocr-eng && \
    rm -rf /var/lib/apt/lists/*

# dejamos el usuario que ya existe en la imagen base
USER app

# no copiamos nada; solo agregamos binarios
CMD ["/bin/sh", "-c", "python -m open_webui"]
