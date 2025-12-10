# llamaindex_service.py
"""
LlamaIndex RAG API con reranking externo.
Imagen docker: registry.arba.gov.ar/infraestructura/llamaindex-rag-api:1.0.0
"""

import os
import logging
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
from llama_index.core import (
    VectorStoreIndex,
    SimpleDirectoryReader,
    Settings,
    StorageContext
)
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.postprocessor import SimilarityPostprocessor
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.llms.openai_like import OpenAILike
from llama_index.embeddings.openai import OpenAIEmbedding
import qdrant_client

# ------------------------------------------------------------------
# 1.  CONFIGURACIÓN BÁSICA
# ------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="LlamaIndex RAG API with Reranking")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------
# 2.  VALIDACIÓN OBLIGATORIA DE VARIABLES DE ENTORNO
#     Si falta alguna el contenedor explota al arrancar → Kubernetes
#     lo restartea y el error queda visible en el describe del pod.
# ------------------------------------------------------------------
_REQUIRED_ENVS = (
    "LLM_PRIMARY_URL",
    "LLM_PRIMARY_MODEL",
    "EMBEDDING_URL",
    "EMBEDDING_MODEL",
    "RERANKER_URL",
    "RERANKER_MODEL",
)
for _var in _REQUIRED_ENVS:
    if os.getenv(_var) is None:
        raise RuntimeError(f"Environment variable {_var} is required")

LLM_PRIMARY_URL       = os.getenv("LLM_PRIMARY_URL")
LLM_PRIMARY_MODEL     = os.getenv("LLM_PRIMARY_MODEL")
LLM_PRIMARY_CONTEXT   = int(os.getenv("LLM_PRIMARY_CONTEXT", "65536"))

EMBEDDING_URL   = os.getenv("EMBEDDING_URL")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL")

RERANKER_URL   = os.getenv("RERANKER_URL")
RERANKER_MODEL = os.getenv("RERANKER_MODEL")

QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant-service")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))

CHUNK_SIZE      = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP   = int(os.getenv("CHUNK_OVERLAP", "200"))
RAG_TOP_K       = int(os.getenv("RAG_TOP_K", "20"))
RERANK_TOP_N    = int(os.getenv("RERANK_TOP_N", "5"))

# ------------------------------------------------------------------
# 3.  MODELOS (LLM + EMBEDDINGS)
#     * Se elimina el parámetro "context_window" que ya NO existe en
#       OpenAILike 0.5.3.  Si tu backend lo necesita, pásalo dentro
#       de extra_body o como header.
# ------------------------------------------------------------------
llm = OpenAILike(
    api_base=LLM_PRIMARY_URL,
    api_key="dummy",               # no se usa pero es obligatorio
    model=LLM_PRIMARY_MODEL,
    is_chat_model=True,
    timeout=120.0,
    # max_tokens se envía en cada llamada, no aquí
)

embed_model = OpenAIEmbedding(
    api_base=EMBEDDING_URL,
    api_key="dummy",
    model_name=EMBEDDING_MODEL,
)

Settings.llm          = llm
Settings.embed_model  = embed_model
Settings.chunk_size   = CHUNK_SIZE
Settings.chunk_overlap= CHUNK_OVERLAP

# ------------------------------------------------------------------
# 4.  CLIENTE QDRANT
# ------------------------------------------------------------------
qdrant_client_instance = qdrant_client.QdrantClient(
    host=QDRANT_HOST,
    port=QDRANT_PORT,
    timeout=60.0
)

logger.info("✅ LlamaIndex API initialized")
logger.info("   LLM : %s @ %s", LLM_PRIMARY_MODEL, LLM_PRIMARY_URL)
logger.info("   Emb : %s @ %s", EMBEDDING_MODEL,   EMBEDDING_URL)
logger.info("   Rer : %s @ %s", RERANKER_MODEL,    RERANKER_URL)
logger.info("   Qdr : %s:%s",   QDRANT_HOST,       QDRANT_PORT)

# ------------------------------------------------------------------
# 5.  RERANKER EXTERNO
# ------------------------------------------------------------------
class CustomReranker:
    """Reranker personalizado usando el servicio BAAI"""
    def __init__(self, url: str, model: str, top_n: int = 5):
        self.url   = url
        self.model = model
        self.top_n = top_n

    async def rerank(self, query: str, documents: List[str]) -> List[dict]:
        async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
            try:
                resp = await client.post(
                    self.url,
                    json={
                        "model": self.model,
                        "query": query,
                        "documents": documents,
                        "top_n": self.top_n,
                    }
                )
                resp.raise_for_status()
                return resp.json()
            except Exception as exc:
                logger.error("Reranker error: %s", exc)
                # fallback: devuelve los primeros N sin modificar
                return [{"index": i, "relevance_score": 1.0}
                        for i in range(min(self.top_n, len(documents)))]


reranker = CustomReranker(
    url=RERANKER_URL,
    model=RERANKER_MODEL,
    top_n=RERANK_TOP_N
)

# ------------------------------------------------------------------
# 6.  MODELOS DE PETICIÓN / RESPUESTA
# ------------------------------------------------------------------
class QueryRequest(BaseModel):
    question: str
    collection: str = "documents"
    use_reranker: bool = True
    top_k: Optional[int] = None
    rerank_top_n: Optional[int] = None


class IngestRequest(BaseModel):
    file_path: str
    collection: str = "documents"


class DocumentResponse(BaseModel):
    text: str
    score: float
    metadata: dict


class QueryResponse(BaseModel):
    answer: str
    sources: List[DocumentResponse]
    reranked: bool


# ------------------------------------------------------------------
# 7.  ENDPOINTS
# ------------------------------------------------------------------
@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "llm_url": LLM_PRIMARY_URL,
        "embedding_url": EMBEDDING_URL,
        "reranker_url": RERANKER_URL,
        "qdrant_host": f"{QDRANT_HOST}:{QDRANT_PORT}"
    }


@app.post("/query", response_model=QueryResponse)
async def query_documents(request: QueryRequest):
    try:
        top_k = request.top_k or RAG_TOP_K
        rerank_top_n = request.rerank_top_n or RERANK_TOP_N

        logger.info("Query: %.100s… | collection=%s top_k=%s rerank=%s",
                    request.question, request.collection, top_k, request.use_reranker)

        # 7-a  Construimos el índice UNA sola vez
        vector_store = QdrantVectorStore(
            client=qdrant_client_instance,
            collection_name=request.collection
        )
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        index   = VectorStoreIndex.from_vector_store(
            vector_store=vector_store,
            storage_context=storage_context
        )

        # 7-b  Retriever a partir de ese índice
        retriever = VectorIndexRetriever(index=index, similarity_top_k=top_k)
        nodes = retriever.retrieve(request.question)
        logger.info("Retrieved %s nodes", len(nodes))

        # 7-c  Reranking opcional
        reranked = False
        if request.use_reranker and nodes:
            try:
                texts = [n.node.get_content() for n in nodes]
                rerank_results = await reranker.rerank(request.question, texts)
                reranked_nodes = []
                for res in rerank_results:
                    idx = res.get("index", res.get("document_index", 0))
                    if idx < len(nodes):
                        node = nodes[idx]
                        node.score = res.get("relevance_score", node.score)
                        reranked_nodes.append(node)
                nodes = reranked_nodes[:rerank_top_n]   # recorte único
                reranked = True
            except Exception as exc:
                logger.error("Reranking failed: %s", exc)

        # 7-d  Query engine con el **mismo** retriever
        query_engine = RetrieverQueryEngine.from_args(
            retriever=retriever,
            node_postprocessors=[SimilarityPostprocessor(similarity_cutoff=0.7)]
        )
        response = query_engine.query(request.question)

        # 7-e  Construimos sources (sin recortar de nuevo)
        sources = []
        for node in nodes:                       # <-- sin [:5] ni [:rerank_top_n]
            sources.append(DocumentResponse(
                text=node.node.get_content()[:500] + "…",
                score=float(node.score or 0.0),
                metadata=node.node.metadata
            ))

        return QueryResponse(
            answer=str(response),
            sources=sources,
            reranked=reranked
        )

    except Exception as exc:
        logger.exception("Query error")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/ingest")
async def ingest_documents(request: IngestRequest):
    try:
        logger.info("Ingesting from %s", request.file_path)
        documents = SimpleDirectoryReader(request.file_path).load_data()
        logger.info("Loaded %s documents", len(documents))

        vector_store = QdrantVectorStore(
            client=qdrant_client_instance,
            collection_name=request.collection
        )
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        _ = VectorStoreIndex.from_documents(
            documents,
            storage_context=storage_context,
            show_progress=True
        )
        logger.info("✅ Ingested %s docs into collection <%s>",
                    len(documents), request.collection)
        return {
            "status": "success",
            "collection": request.collection,
            "documents_processed": len(documents)
        }
    except Exception as exc:
        logger.exception("Ingest error")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/collections")
async def list_collections():
    try:
        cols = qdrant_client_instance.get_collections()
        return {"collections": [c.name for c in cols.collections]}
    except Exception as exc:
        logger.exception("List collections error")
        raise HTTPException(status_code=500, detail=str(exc))


# ------------------------------------------------------------------
# 8.  ARRANCAR SERVER
# ------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)