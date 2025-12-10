# Pipeline Personalizado para Open WebUI
# Este pipeline intercepta las consultas y usa el servicio LlamaIndex con reranking

from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import requests
import os

class Pipeline:
    """
    Pipeline avanzado de RAG con reranking para Open WebUI
    
    Flujo:
    1. Usuario hace pregunta en Open WebUI
    2. Pipeline intercepta la consulta
    3. Llama a LlamaIndex API con reranking habilitado
    4. Devuelve respuesta mejorada
    """
    
    class Valves(BaseModel):
        """Configuración del pipeline"""
        LLAMAINDEX_API_URL: str = "http://llamaindex-api-service.rag-system.svc.cluster.local:8000"
        COLLECTION_NAME: str = "documents"
        ENABLE_RERANKER: bool = True
        TOP_K: int = 20
        RERANK_TOP_N: int = 5
        INCLUDE_SOURCES: bool = True
        MIN_SIMILARITY_SCORE: float = 0.7

    def __init__(self):
        self.valves = self.Valves()
        self.name = "RAG Pipeline con Reranking"
        self.description = "Pipeline avanzado de RAG usando LlamaIndex con BAAI reranker"

    async def on_startup(self):
        """Se ejecuta al iniciar el pipeline"""
        print(f"✅ {self.name} iniciado")
        print(f"   API: {self.valves.LLAMAINDEX_API_URL}")
        print(f"   Reranker: {'Habilitado' if self.valves.ENABLE_RERANKER else 'Deshabilitado'}")

    async def on_shutdown(self):
        """Se ejecuta al detener el pipeline"""
        print(f"🛑 {self.name} detenido")

    def pipe(
        self, 
        user_message: str, 
        model_id: str, 
        messages: List[dict], 
        body: dict
    ) -> str | Dict[str, Any]:
        """
        Procesa el mensaje del usuario
        
        Args:
            user_message: Mensaje actual del usuario
            model_id: ID del modelo seleccionado
            messages: Historial completo de conversación
            body: Configuración adicional
            
        Returns:
            Respuesta procesada con contexto RAG
        """
        
        try:
            # Verificar si hay documentos en la colección
            collections_response = requests.get(
                f"{self.valves.LLAMAINDEX_API_URL}/collections",
                timeout=5
            )
            
            if collections_response.status_code != 200:
                return "⚠️ Error: No se puede conectar al servicio RAG"
            
            collections = collections_response.json().get("collections", [])
            
            if self.valves.COLLECTION_NAME not in collections:
                return f"⚠️ La colección '{self.valves.COLLECTION_NAME}' no existe. Por favor, ingesta documentos primero."
            
            # Consultar con RAG
            query_payload = {
                "question": user_message,
                "collection": self.valves.COLLECTION_NAME,
                "use_reranker": self.valves.ENABLE_RERANKER,
                "top_k": self.valves.TOP_K,
                "rerank_top_n": self.valves.RERANK_TOP_N
            }
            
            response = requests.post(
                f"{self.valves.LLAMAINDEX_API_URL}/query",
                json=query_payload,
                timeout=60
            )
            
            if response.status_code != 200:
                error_detail = response.json().get("detail", "Error desconocido")
                return f"❌ Error en RAG: {error_detail}"
            
            result = response.json()
            answer = result.get("answer", "")
            sources = result.get("sources", [])
            reranked = result.get("reranked", False)
            
            # Construir respuesta mejorada
            output = answer
            
            # Agregar información sobre el proceso
            if reranked:
                output += f"\n\n🔍 *Respuesta mejorada con reranking*"
            
            # Agregar fuentes si está habilitado
            if self.valves.INCLUDE_SOURCES and sources:
                output += "\n\n📚 **Fuentes consultadas:**\n"
                for i, source in enumerate(sources, 1):
                    score = source.get("score", 0)
                    if score >= self.valves.MIN_SIMILARITY_SCORE:
                        text_preview = source.get("text", "")[:150]
                        metadata = source.get("metadata", {})
                        file_name = metadata.get("file_name", "Desconocido")
                        
                        output += f"\n{i}. **{file_name}** (relevancia: {score:.2f})\n"
                        output += f"   _{text_preview}..._\n"
            
            return output
            
        except requests.exceptions.Timeout:
            return "⏱️ Timeout: La consulta tardó demasiado. Intenta con una pregunta más específica."
        
        except requests.exceptions.ConnectionError:
            return "🔌 Error de conexión: No se puede alcanzar el servicio RAG. Verifica que esté ejecutándose."
        
        except Exception as e:
            return f"❌ Error inesperado: {str(e)}"


# Función auxiliar para configuración avanzada
def get_advanced_config() -> dict:
    """
    Configuración avanzada del pipeline
    Puedes modificar estos valores según tus necesidades
    """
    return {
        "chunk_strategies": {
            "default": {"size": 1000, "overlap": 200},
            "precise": {"size": 500, "overlap": 100},
            "broad": {"size": 2000, "overlap": 400}
        },
        "retrieval_strategies": {
            "fast": {"top_k": 10, "rerank_top_n": 3},
            "balanced": {"top_k": 20, "rerank_top_n": 5},
            "comprehensive": {"top_k": 30, "rerank_top_n": 10}
        },
        "supported_collections": [
            "documents",
            "knowledge-base",
            "manuals",
            "policies"
        ]
    }
