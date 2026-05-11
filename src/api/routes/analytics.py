from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.api.dependencies import get_db_engine

router = APIRouter(prefix="/analytics", tags=["analytics"])


class HourlyAnalytics(BaseModel):
    node_id: str
    division: Optional[str]
    hour_start: datetime
    total_consumption_wh: float
    avg_power_w: Optional[float]
    peak_power_w: Optional[float]
    reading_count: Optional[int]


class DailyAnalytics(BaseModel):
    node_id: str
    division: Optional[str]
    date: date
    total_consumption_wh: float
    avg_power_w: Optional[float]
    peak_power_w: Optional[float]
    reading_count: Optional[int]


@router.get("/hourly", response_model=List[HourlyAnalytics])
def get_hourly_analytics(
    node_id: Optional[str] = Query(None, description="Filter by node ID"),
    division: Optional[str] = Query(None, description="Filter by division"),
    start: Optional[int] = Query(None, description="Start time (Unix epoch ms, inclusive)"),
    end: Optional[int] = Query(None, description="End time (Unix epoch ms, inclusive)"),
    limit: int = Query(100, ge=1, le=1000, description="Max records to return"),
    engine: Engine = Depends(get_db_engine),
):
    """Return hourly energy analytics rollups from PostgreSQL, newest first."""
    filters = []
    params: dict = {"limit": limit}

    if node_id:
        filters.append("node_id = :node_id")
        params["node_id"] = node_id
    if division:
        filters.append("division = :division")
        params["division"] = division
    if start is not None:
        filters.append("hour_start >= to_timestamp(:start / 1000.0)")
        params["start"] = start
    if end is not None:
        filters.append("hour_start <= to_timestamp(:end / 1000.0)")
        params["end"] = end

    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    query = text(f"""
        SELECT node_id, division, hour_start, total_consumption_wh, avg_power_w, peak_power_w, reading_count
        FROM energy_analytics_hourly
        {where}
        ORDER BY hour_start DESC
        LIMIT :limit
    """)

    try:
        with engine.connect() as conn:
            rows = conn.execute(query, params).mappings().all()
        return [dict(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database error: {e}")


@router.get("/daily", response_model=List[DailyAnalytics])
def get_daily_analytics(
    node_id: Optional[str] = Query(None, description="Filter by node ID"),
    division: Optional[str] = Query(None, description="Filter by division"),
    start: Optional[str] = Query(None, description="Start date (YYYY-MM-DD, inclusive)"),
    end: Optional[str] = Query(None, description="End date (YYYY-MM-DD, inclusive)"),
    limit: int = Query(100, ge=1, le=1000, description="Max records to return"),
    engine: Engine = Depends(get_db_engine),
):
    """Return daily energy analytics rollups from PostgreSQL, newest first."""
    filters = []
    params: dict = {"limit": limit}

    if node_id:
        filters.append("node_id = :node_id")
        params["node_id"] = node_id
    if division:
        filters.append("division = :division")
        params["division"] = division
    if start:
        filters.append("date >= :start::date")
        params["start"] = start
    if end:
        filters.append("date <= :end::date")
        params["end"] = end

    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    query = text(f"""
        SELECT node_id, division, date, total_consumption_wh, avg_power_w, peak_power_w, reading_count
        FROM energy_analytics_daily
        {where}
        ORDER BY date DESC
        LIMIT :limit
    """)

    try:
        with engine.connect() as conn:
            rows = conn.execute(query, params).mappings().all()
        return [dict(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database error: {e}")
