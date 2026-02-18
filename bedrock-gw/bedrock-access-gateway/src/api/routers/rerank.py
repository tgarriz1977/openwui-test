from typing import Annotated

from fastapi import APIRouter, Body, Depends

from api.auth import api_key_auth
from api.models.bedrock import get_rerank_model
from api.schema import RerankRequest, RerankResponse

router = APIRouter(
    prefix="/rerank",
    dependencies=[Depends(api_key_auth)],
)


@router.post("", response_model=RerankResponse)
async def rerank(
    rerank_request: Annotated[
        RerankRequest,
        Body(
            examples=[
                {
                    "model": "cohere.rerank-v3-5:0",
                    "query": "What is the capital of France?",
                    "documents": [
                        "Paris is the capital of France.",
                        "Berlin is the capital of Germany.",
                        "Madrid is the capital of Spain.",
                    ],
                    "top_n": 3,
                }
            ],
        ),
    ],
):
    model = get_rerank_model()
    return model.rerank(rerank_request)
