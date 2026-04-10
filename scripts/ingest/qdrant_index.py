import os
import hashlib
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, 
    Filter, FieldCondition, MatchValue
)
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "actas_colegio")
BEDROCK_URL = os.getenv("BEDROCK_URL", "http://localhost:8080")
BEDROCK_API_KEY = os.getenv("BEDROCK_API_KEY")

# Usamos el modelo de embeddings de Bedrock via gateway
EMBEDDING_MODEL = "amazon.titan-embed-text-v2:0"
VECTOR_SIZE = 1024

qdrant = QdrantClient(url=QDRANT_URL)

client = OpenAI(
    base_url=f"{BEDROCK_URL}/api/v1",
    api_key=BEDROCK_API_KEY
)

def asegurar_coleccion():
    """Crea la colección en Qdrant si no existe"""
    colecciones = [c.name for c in qdrant.get_collections().collections]
    if QDRANT_COLLECTION not in colecciones:
        qdrant.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=VectorParams(
                size=VECTOR_SIZE,
                distance=Distance.COSINE
            )
        )
        print(f"[Qdrant] Colección '{QDRANT_COLLECTION}' creada")
    else:
        print(f"[Qdrant] Colección '{QDRANT_COLLECTION}' ya existe")

def generar_embedding(texto: str) -> list:
    """Genera embedding via Bedrock gateway"""
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texto
    )
    return response.data[0].embedding

def chunk_id(texto: str, acta_numero: int, indice: int) -> int:
    """Genera un ID numérico único para cada chunk"""
    hash_str = f"{acta_numero}_{indice}_{texto[:50]}"
    return int(hashlib.md5(hash_str.encode()).hexdigest()[:8], 16)

def indexar_acta(markdown: str, datos: dict, acta_id: int):
    """
    Indexa el acta completa en Qdrant.
    Estrategia: un chunk por nota, con metadata para filtrado.
    """
    asegurar_coleccion()
    
    acta_numero = datos["acta"]["acta_numero"]
    fecha = datos["acta"].get("fecha", "")
    points = []
    indice = 0
    
    # Indexa cada nota como un chunk independiente
    secciones = [
        ("notas_me_mt", "ME/MT"),
        ("notas_distritos", "Distritos"),
        ("notas_as", "AS"),
        ("notas_at", "AT"),
    ]
    
    for clave_seccion, nombre_seccion in secciones:
        for nota in datos.get(clave_seccion, []):
            # Construye texto del chunk con contexto
            texto_chunk = f"""Acta N° {acta_numero} — {fecha}
Sección: {nota.get('seccion', nombre_seccion)}
Código: {nota.get('codigo_nota', '')}
Tema: {nota.get('tema', '')}
Descripción: {nota.get('descripcion', '')}
Resolución: {nota.get('resolucion', '')}"""
            
            embedding = generar_embedding(texto_chunk)
            
            points.append(PointStruct(
                id=chunk_id(texto_chunk, acta_numero, indice),
                vector=embedding,
                payload={
                    "acta_numero": acta_numero,
                    "acta_id": acta_id,
                    "fecha": fecha,
                    "seccion": nota.get("seccion", nombre_seccion),
                    "codigo_nota": nota.get("codigo_nota", ""),
                    "tema": nota.get("tema", ""),
                    "texto_completo": texto_chunk
                }
            ))
            indice += 1
    
    # Indexa temas varios
    for tema in datos.get("temas_varios", []):
        texto_chunk = f"""Acta N° {acta_numero} — {fecha}
Sección: Temas Varios
Punto {tema.get('numero_punto', '')}: {tema.get('titulo', '')}
Descripción: {tema.get('descripcion', '')}
Resolución: {tema.get('resolucion', '')}"""
        
        embedding = generar_embedding(texto_chunk)
        
        points.append(PointStruct(
            id=chunk_id(texto_chunk, acta_numero, indice),
            vector=embedding,
            payload={
                "acta_numero": acta_numero,
                "acta_id": acta_id,
                "fecha": fecha,
                "seccion": "Temas Varios",
                "codigo_nota": f"TV-{tema.get('numero_punto', '')}",
                "tema": tema.get("titulo", ""),
                "texto_completo": texto_chunk
            }
        ))
        indice += 1
    
    # Sube en lotes de 50
    lote_size = 50
    for i in range(0, len(points), lote_size):
        lote = points[i:i+lote_size]
        qdrant.upsert(collection_name=QDRANT_COLLECTION, points=lote)
    
    print(f"[Qdrant] OK — {len(points)} chunks indexados para acta {acta_numero}")
