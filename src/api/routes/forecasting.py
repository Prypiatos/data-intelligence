from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.api.dependencies import get_db_engine

router = APIRouter(prefix="/forecast", tags=["forecasting"])


class ForecastRecord(BaseModel):
    node_id: str
    timestamp: int
    predicted_consumption: float


@router.get("/forecasts", response_model=List[ForecastRecord])
def get_forecasts(
    node_id: Optional[str] = Query(None, description="Filter by node ID"),
    limit: int = Query(100, ge=1, le=1000, description="Max records to return"),
    engine: Engine = Depends(get_db_engine),
):
    """Return stored forecast rows from PostgreSQL, newest first."""
    filters = []
    params: dict = {"limit": limit}

    if node_id:
        filters.append("node_id = :node_id")
        params["node_id"] = node_id

    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    query = text(f"""
        SELECT node_id, timestamp, predicted_consumption
        FROM forecasts
        {where}
        ORDER BY timestamp ASC
        LIMIT :limit
    """)

    try:
        with engine.connect() as conn:
            rows = conn.execute(query, params).mappings().all()
        return [dict(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database error: {e}")
