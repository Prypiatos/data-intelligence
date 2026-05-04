from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.api.dependencies import get_db_engine

router = APIRouter(prefix="/anomalies", tags=["anomalies"])


class AnomalyRecord(BaseModel):
    node_id: str
    timestamp: int
    anomaly_type: str
    score: float
    severity: str


@router.get("", response_model=List[AnomalyRecord])
def get_anomalies(
    node_id: Optional[str] = Query(None, description="Filter by node ID"),
    severity: Optional[str] = Query(None, description="Filter by severity: high, medium, normal"),
    limit: int = Query(100, ge=1, le=1000, description="Max records to return"),
    engine: Engine = Depends(get_db_engine),
):
    """Return anomaly records from PostgreSQL, newest first."""
    filters = []
    params: dict = {"limit": limit}

    if node_id:
        filters.append("node_id = :node_id")
        params["node_id"] = node_id
    if severity:
        filters.append("severity = :severity")
        params["severity"] = severity

    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    query = text(f"""
        SELECT node_id, timestamp, anomaly_type, score, severity
        FROM anomaly_records
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
