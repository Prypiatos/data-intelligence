"""Shared data loader for the RECON-SL Sri Lankan smart meter dataset.

Default location: ~/Downloads/archive-2/data/data/consumption_data/smart_meter/15min_interval/
Override with the RECON_SL_DIR environment variable.
"""

import os
from pathlib import Path

import numpy as np
import pandas as pd

_DEFAULT_DIR = (
    Path.home()
    / "Downloads/archive-2/data/data/consumption_data/smart_meter/15min_interval"
)

_FILES = ["smart_15min_1.csv", "smart_15min_2.csv", "smart_15min_3.csv"]

_USECOLS = [
    "household_ID",
    "timestamp",
    "avgimportkw(kw)",
    "phaseainstvoltage(v)",
    "phaseainstcurrent(a)",
    "powerfactor",
]


def load_recon_sl(
    data_dir: Path | str | None = None,
    max_households: int | None = None,
) -> pd.DataFrame:
    """Load and clean RECON-SL 15-minute smart meter data.

    Returns a DataFrame with columns:
        node_id, timestamp_ms, datetime, power_w, voltage, current, energy_wh, power_factor
    """
    if data_dir is None:
        data_dir = Path(os.getenv("RECON_SL_DIR", str(_DEFAULT_DIR)))
    else:
        data_dir = Path(data_dir)

    chunks = []
    for name in _FILES:
        path = data_dir / name
        print(f"  Loading {name} ...")
        df = pd.read_csv(path, usecols=_USECOLS, low_memory=False)
        chunks.append(df)

    df = pd.concat(chunks, ignore_index=True)
    print(f"  Loaded {len(df):,} rows, {df['household_ID'].nunique():,} households")

    df = df.rename(columns={
        "household_ID": "node_id",
        "avgimportkw(kw)": "avg_import_kw",
        "phaseainstvoltage(v)": "voltage",
        "phaseainstcurrent(a)": "current",
        "powerfactor": "power_factor",
    })

    # Timestamp
    df["timestamp_ms"] = pd.to_numeric(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp_ms", "avg_import_kw"])
    df["timestamp_ms"] = df["timestamp_ms"].astype("int64")
    df["datetime"] = pd.to_datetime(df["timestamp_ms"], unit="ms")

    # Power: kW → W, no negatives
    df["power_w"] = (df["avg_import_kw"] * 1000.0).clip(lower=0)

    # Energy per 15-min interval: kW × 0.25 h × 1000 = Wh
    df["energy_wh"] = df["avg_import_kw"] * 0.25 * 1000.0

    # Voltage: Sri Lanka nominal is 230 V, keep plausible range
    df["voltage"] = pd.to_numeric(df["voltage"], errors="coerce")
    df = df[(df["voltage"] >= 200) & (df["voltage"] <= 260)]

    # Power factor
    df["power_factor"] = (
        pd.to_numeric(df["power_factor"], errors="coerce").fillna(0.85).clip(0.1, 1.0)
    )

    # Current: use measured value; derive from P = V × I × PF where missing
    df["current"] = pd.to_numeric(df["current"], errors="coerce")
    derived = df["power_w"] / (df["voltage"] * df["power_factor"] + 1e-9)
    df["current"] = df["current"].where(
        df["current"].notna() & (df["current"] > 0), other=derived
    )
    df["current"] = df["current"].clip(0, 150)

    if max_households is not None:
        keep = df["node_id"].unique()[:max_households]
        df = df[df["node_id"].isin(keep)]

    return df[
        ["node_id", "timestamp_ms", "datetime", "power_w", "voltage", "current", "energy_wh", "power_factor"]
    ].reset_index(drop=True)
