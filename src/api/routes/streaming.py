from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.api.dependencies import get_db_engine

router = APIRouter(prefix="/stream", tags=["streaming"])


class StreamSummary(BaseModel):
    node_id: str
    window_start: int
    window_end: int
    avg_power: float
    max_power: float
    avg_voltage: Optional[float]
    avg_current: Optional[float]
    avg_energy_wh: Optional[float]
    record_count: int


@router.get("/summary", response_model=List[StreamSummary])
def get_stream_summary(
    node_id: Optional[str] = Query(None, description="Filter by node ID"),
    limit: int = Query(100, ge=1, le=1000, description="Max records to return"),
    engine: Engine = Depends(get_db_engine),
):
    """Return per-node window summaries produced by the Flink streaming job."""
    query = "SELECT node_id, window_start, window_end, avg_power, max_power, avg_voltage, avg_current, avg_energy_wh, record_count FROM stream_summaries"
    params: dict = {"limit": limit}

    if node_id:
        query += " WHERE node_id = :node_id"
        params["node_id"] = node_id

    query += " ORDER BY window_start DESC LIMIT :limit"

    try:
        with engine.connect() as conn:
            rows = conn.execute(text(query), params).mappings().all()
        return [dict(row) for row in rows]
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database error: {e}")
