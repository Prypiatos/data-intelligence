import os
import time
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.api.dependencies import get_db_engine

router = APIRouter(prefix="/nodes", tags=["nodes"])

LEARNING_PERIOD_DAYS = int(os.getenv("LEARNING_PERIOD_DAYS", "30"))


class NodeStatus(BaseModel):
    node_id: str
    learning_mode: bool
    first_seen_ms: Optional[int] = None
    days_since_first_seen: Optional[float] = None
    days_remaining: Optional[float] = None


def _compute_status(node_id: str, first_seen_ms: Optional[int]) -> NodeStatus:
    if first_seen_ms is None:
        return NodeStatus(
            node_id=node_id,
            learning_mode=True,
            days_remaining=float(LEARNING_PERIOD_DAYS),
        )
    now_ms = int(time.time() * 1000)
    days_since = (now_ms - first_seen_ms) / (24 * 3600 * 1000)
    learning_mode = days_since < LEARNING_PERIOD_DAYS
    days_remaining = (
        max(0.0, LEARNING_PERIOD_DAYS - days_since) if learning_mode else 0.0
    )
    return NodeStatus(
        node_id=node_id,
        learning_mode=learning_mode,
        first_seen_ms=first_seen_ms,
        days_since_first_seen=round(days_since, 1),
        days_remaining=round(days_remaining, 1),
    )


@router.get("", response_model=List[NodeStatus])
def get_all_nodes(engine: Engine = Depends(get_db_engine)):
    """Return all known nodes with their learning mode status."""
    query = text("""
        SELECT node_id, MIN(timestamp) AS first_seen_ms
        FROM telemetry_readings
        GROUP BY node_id
        ORDER BY node_id
    """)
    try:
        with engine.connect() as conn:
            rows = conn.execute(query).mappings().all()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database error: {e}")
    return [_compute_status(row["node_id"], row["first_seen_ms"]) for row in rows]


@router.get("/{node_id}/status", response_model=NodeStatus)
def get_node_status(
    node_id: str = Path(..., description="Node ID"),
    engine: Engine = Depends(get_db_engine),
):
    """Return learning mode status for a specific node."""
    query = text("""
        SELECT MIN(timestamp) AS first_seen_ms
        FROM telemetry_readings
        WHERE node_id = :node_id
    """)
    try:
        with engine.connect() as conn:
            row = conn.execute(query, {"node_id": node_id}).mappings().one_or_none()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database error: {e}")
    if row is None or row["first_seen_ms"] is None:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")
    return _compute_status(node_id, row["first_seen_ms"])
