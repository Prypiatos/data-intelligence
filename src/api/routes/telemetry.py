import os
import re
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from influxdb_client import InfluxDBClient
from pydantic import BaseModel

from src.api.dependencies import get_influx_client

INFLUX_BUCKET = os.getenv("INFLUXDB_BUCKET", "energy_telemetry")
INFLUX_ORG = os.getenv("INFLUXDB_ORG", "energy-org")

_NODE_ID_RE = re.compile(r"^[\w\-]+$")  # guard against Flux injection

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


class TelemetryReading(BaseModel):
    node_id: str
    timestamp: int
    voltage: float
    current: float
    power: float
    energy_wh: float


def _ms_to_rfc3339(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@router.get("/history", response_model=List[TelemetryReading])
def get_telemetry_history(
    node_id: Optional[str] = Query(None, description="Filter by node ID"),
    start: Optional[int] = Query(None, description="Start time (Unix epoch ms, inclusive)"),
    end: Optional[int] = Query(None, description="End time (Unix epoch ms, inclusive)"),
    limit: int = Query(100, ge=1, le=1000, description="Max records to return"),
    client: InfluxDBClient = Depends(get_influx_client),
):
    """Return raw telemetry readings from InfluxDB, newest first."""
    if node_id and not _NODE_ID_RE.match(node_id):
        raise HTTPException(status_code=400, detail="Invalid node_id format")

    start_str = _ms_to_rfc3339(start) if start is not None else "-30d"
    stop_str = _ms_to_rfc3339(end) if end is not None else "now()"
    node_filter = f'|> filter(fn: (r) => r.node_id == "{node_id}")' if node_id else ""

    flux = f"""
        from(bucket: "{INFLUX_BUCKET}")
          |> range(start: {start_str}, stop: {stop_str})
          |> filter(fn: (r) => r._measurement == "telemetry")
          {node_filter}
          |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
          |> group()
          |> sort(columns: ["_time"], desc: true)
          |> limit(n: {limit})
    """

    try:
        tables = client.query_api().query(flux, org=INFLUX_ORG)
        results = []
        for table in tables:
            for record in table.records:
                ts_ms = int(record.get_time().timestamp() * 1000)
                v = record.values
                results.append(TelemetryReading(
                    node_id=v.get("node_id", ""),
                    timestamp=ts_ms,
                    voltage=float(v.get("voltage") or 0),
                    current=float(v.get("current") or 0),
                    power=float(v.get("power") or 0),
                    energy_wh=float(v.get("energy_wh") or 0),
                ))
        return results
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"InfluxDB error: {e}")
