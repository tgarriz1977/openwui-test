# Docling Serve - Mejorado para Tablas Financieras

Imagen Docker extendida de `quay.io/docling-project/docling-serve` con extracción especializada de tablas usando **pdfplumber**.

## 🎯 Mejoras

- **Extracción de tablas**: Usa `pdfplumber` para detectar y extraer tablas estructuradas
- **Detección financiera**: Identifica automáticamente tablas financieras (presupuestos, tesorería, etc.)
- **Formato Markdown**: Tablas formateadas profesionalmente
- **100% Compatible**: Mantiene la misma API REST que docling-serve original

## 🏗️ Build

```bash
# Login al registry de AWS
aws ecr get-login-password --region us-east-2 | docker login --username AWS --password-stdin 982170164096.dkr.ecr.us-east-2.amazonaws.com

# Build de la imagen
docker build -t docling-serve-enhanced:latest .

# Tag para ECR
docker tag docling-serve-enhanced:latest 982170164096.dkr.ecr.us-east-2.amazonaws.com/docling-serve-enhanced:latest

# Push
docker push 982170164096.dkr.ecr.us-east-2.amazonaws.com/docling-serve-enhanced:latest
```

## 🚀 API Endpoints

### Health Check
```bash
curl http://localhost:5001/health
```

Respuesta:
```json
{
  "status": "ok",
  "service": "docling-serve-enhanced",
  "pdfplumber_available": true,
  "features": ["ocr", "table_extraction", "financial_tables"]
}
```

### Conversión de PDF
```bash
curl -X POST http://localhost:5001/v1/convert/file \
  -F "file=@ACTA.pdf" \
  -H "Content-Type: multipart/form-data"
```

Respuesta:
```json
{
  "text": "# Markdown con tablas...",
  "metadata": {
    "filename": "ACTA.pdf",
    "tables_extracted": 5,
    "financial_tables": 2,
    "processor": "docling+pdfplumber"
  }
}
```

## 🔧 Uso Local

```bash
# Ejecutar contenedor
docker run -p 5001:5001 docling-serve-enhanced:latest

# Probar
curl http://localhost:5001/health
```

## 📋 Comparativa

| Feature | docling-serve Original | Esta Imagen |
|---------|------------------------|-------------|
| OCR de texto | ✅ | ✅ |
| Tablas estructuradas | ⚠️ Básico | ✅ Mejorado con pdfplumber |
| Detección financiera | ❌ | ✅ Automática |
| Markdown de tablas | ⚠️ Desordenado | ✅ Formateado |
| API REST | `/v1/convert/file` | `/v1/convert/file` (misma) |

## 🔄 Despliegue en Kubernetes

Después del push, actualizar el deployment:

```yaml
# 07-docling.yaml
spec:
  template:
    spec:
      containers:
      - name: docling
        image: 982170164096.dkr.ecr.us-east-2.amazonaws.com/docling-serve-enhanced:latest
```

ArgoCD sincronizará automáticamente el cambio.

## 📝 Notas

- La imagen mantiene **compatibilidad 100%** con la API original
- Si pdfplumber falla, cae gracefully al comportamiento original de docling
- Las tablas financieras detectadas se marcan con `## 📊 Tablas Financieras Extraídas`
