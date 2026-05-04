from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.engine import Engine

from src.api.dependencies import get_db_engine
from src.optimization.recommendations import run as run_recommendations

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


class RecommendationItem(BaseModel):
    node_id: str
    type: str
    severity: str
    message: str
    generated_at: str
    metadata: Dict[str, Any]


@router.get("", response_model=List[RecommendationItem])
def get_recommendations(engine: Engine = Depends(get_db_engine)):
    """Generate and return energy optimization recommendations."""
    try:
        return run_recommendations(engine=engine)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to generate recommendations: {e}")
