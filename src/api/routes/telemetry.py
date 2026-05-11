from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.api.dependencies import get_db_engine

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


class TelemetryReading(BaseModel):
    node_id: str
    timestamp: int
    voltage: float
    current: float
    power: float
    energy_wh: float


@router.get("/history", response_model=List[TelemetryReading])
def get_telemetry_history(
    node_id: Optional[str] = Query(None, description="Filter by node ID"),
    start: Optional[int] = Query(None, description="Start time (Unix epoch ms, inclusive)"),
    end: Optional[int] = Query(None, description="End time (Unix epoch ms, inclusive)"),
    limit: int = Query(100, ge=1, le=1000, description="Max records to return"),
    engine: Engine = Depends(get_db_engine),
):
    """Return raw telemetry readings from PostgreSQL, newest first."""
    filters = []
    params: dict = {"limit": limit}

    if node_id:
        filters.append("node_id = :node_id")
        params["node_id"] = node_id
    if start is not None:
        filters.append("timestamp >= :start")
        params["start"] = start
    if end is not None:
        filters.append("timestamp <= :end")
        params["end"] = end

    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    query = text(f"""
        SELECT node_id, timestamp, voltage, current, power, energy_wh
        FROM telemetry_readings
        {where}
        ORDER BY timestamp DESC
        LIMIT :limit
    """)

    try:
        with engine.connect() as conn:
            rows = conn.execute(query, params).mappings().all()
        return [dict(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database error: {e}")
