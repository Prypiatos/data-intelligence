"""
Optimization recommendations engine.

Reads latest anomaly scores and forecasts from PostgreSQL and applies
rules to produce structured recommendations served by the API.

Depends on: issues #20 (anomaly records), #21 (forecast records)
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
POSTGRES_DB = os.getenv("POSTGRES_DB", "energy_db")

HIGH_CONSUMPTION_WATTS = float(os.getenv("HIGH_CONSUMPTION_THRESHOLD", "800"))
PEAK_SHIFT_PERCENTILE = 90  # flag hours in the top 10% of forecast as peaks
ANOMALY_LOOKBACK_HOURS = 6  # only consider anomalies from the last N hours


@dataclass
class Recommendation:
    node_id: str
    type: str  # "high_anomaly" | "load_shift" | "high_consumption"
    severity: str  # "high" | "medium" | "low"
    message: str
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "type": self.type,
            "severity": self.severity,
            "message": self.message,
            "generated_at": self.generated_at.isoformat(),
            "metadata": self.metadata,
        }


def _get_engine():
    url = (
        f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
        f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )
    return create_engine(url)


def fetch_anomalies(engine=None) -> pd.DataFrame:
    """Return anomaly records from the last ANOMALY_LOOKBACK_HOURS hours."""
    if engine is None:
        engine = _get_engine()
    query = text(f"""
        SELECT node_id, timestamp, anomaly_score, severity
        FROM anomaly_records
        WHERE timestamp >= EXTRACT(EPOCH FROM NOW() - INTERVAL '{ANOMALY_LOOKBACK_HOURS} hours') * 1000
        ORDER BY timestamp DESC
        """)
    df = pd.read_sql(query, engine)
    logger.info(f"Fetched {len(df)} anomaly records")
    return df


def fetch_forecasts(engine=None) -> pd.DataFrame:
    """Return forecast rows for the next 24 hours."""
    if engine is None:
        engine = _get_engine()
    query = text("""
        SELECT node_id, timestamp, predicted_consumption
        FROM forecasts
        WHERE timestamp >= EXTRACT(EPOCH FROM NOW()) * 1000
          AND timestamp <  EXTRACT(EPOCH FROM NOW() + INTERVAL '24 hours') * 1000
        ORDER BY node_id, timestamp
        """)
    df = pd.read_sql(query, engine)
    logger.info(f"Fetched {len(df)} forecast rows")
    return df


def _anomaly_recommendations(anomalies: pd.DataFrame) -> list[Recommendation]:
    recs: list[Recommendation] = []
    if anomalies.empty:
        return recs

    # Keep the worst anomaly per node in the lookback window
    worst = (
        anomalies[anomalies["severity"].isin(["high", "medium"])]
        .sort_values("anomaly_score")  # lower score = more anomalous
        .groupby("node_id")
        .first()
        .reset_index()
    )

    for _, row in worst.iterrows():
        severity = row["severity"]
        recs.append(
            Recommendation(
                node_id=row["node_id"],
                type="high_anomaly",
                severity=severity,
                message=(
                    f"Node {row['node_id']} flagged with {severity}-severity anomaly "
                    f"(score {row['anomaly_score']:.3f}). Inspect for irregular consumption."
                ),
                metadata={"anomaly_score": float(row["anomaly_score"])},
            )
        )
    return recs


def _load_shift_recommendations(forecasts: pd.DataFrame) -> list[Recommendation]:
    recs: list[Recommendation] = []
    if forecasts.empty:
        return recs

    forecasts = forecasts.copy()
    forecasts["dt"] = pd.to_datetime(forecasts["timestamp"], unit="ms", utc=True)
    forecasts["hour"] = forecasts["dt"].dt.hour

    threshold = forecasts["predicted_consumption"].quantile(PEAK_SHIFT_PERCENTILE / 100)

    peak_nodes = (
        forecasts[forecasts["predicted_consumption"] >= threshold]
        .groupby("node_id")
        .agg(
            peak_hours=("hour", lambda h: sorted(h.unique().tolist())),
            max_consumption=("predicted_consumption", "max"),
        )
        .reset_index()
    )

    for _, row in peak_nodes.iterrows():
        hours_str = ", ".join(f"{h:02d}:00" for h in row["peak_hours"])
        recs.append(
            Recommendation(
                node_id=row["node_id"],
                type="load_shift",
                severity="medium",
                message=(
                    f"Node {row['node_id']} forecast shows peak consumption "
                    f"({row['max_consumption']:.0f}W) at {hours_str}. "
                    "Consider shifting deferrable loads to off-peak hours."
                ),
                metadata={
                    "peak_hours": row["peak_hours"],
                    "max_consumption_watts": float(row["max_consumption"]),
                },
            )
        )
    return recs


def _high_consumption_recommendations(forecasts: pd.DataFrame) -> list[Recommendation]:
    recs: list[Recommendation] = []
    if forecasts.empty:
        return recs

    over_threshold = (
        forecasts[forecasts["predicted_consumption"] >= HIGH_CONSUMPTION_WATTS]
        .groupby("node_id")["predicted_consumption"]
        .max()
        .reset_index()
    )

    for _, row in over_threshold.iterrows():
        recs.append(
            Recommendation(
                node_id=row["node_id"],
                type="high_consumption",
                severity="high",
                message=(
                    f"Node {row['node_id']} forecast exceeds {HIGH_CONSUMPTION_WATTS:.0f}W "
                    f"(peak: {row['predicted_consumption']:.0f}W). Review connected loads."
                ),
                metadata={"max_consumption_watts": float(row["predicted_consumption"])},
            )
        )
    return recs


def generate_recommendations(
    anomalies: pd.DataFrame,
    forecasts: pd.DataFrame,
) -> list[Recommendation]:
    """Apply all rules and return a deduplicated list of recommendations."""
    recs: list[Recommendation] = []
    recs.extend(_anomaly_recommendations(anomalies))
    recs.extend(_high_consumption_recommendations(forecasts))
    recs.extend(_load_shift_recommendations(forecasts))

    # If a node already has a high_consumption rec, skip the load_shift for it
    seen_high = {r.node_id for r in recs if r.type == "high_consumption"}
    recs = [r for r in recs if not (r.type == "load_shift" and r.node_id in seen_high)]

    logger.info(f"Generated {len(recs)} recommendations")
    return recs


def run(engine=None) -> list[dict]:
    """Fetch data, apply rules, return recommendations as dicts for the API."""
    if engine is None:
        engine = _get_engine()
    anomalies = fetch_anomalies(engine)
    forecasts = fetch_forecasts(engine)
    recs = generate_recommendations(anomalies, forecasts)
    return [r.to_dict() for r in recs]
