import io
from docling.document_converter import DocumentConverter
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI()
conv = DocumentConverter()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/v1/convert/file")
def convert(file: UploadFile = File(...)):   # <-- obligatorio, sin default
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(422, "PDF required")
    content = file.file.read()
    result = conv.convert(io.BytesIO(content))
    return JSONResponse({"text": result.document.export_to_markdown()})

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5001)
