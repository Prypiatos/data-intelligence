CREATE TABLE IF NOT EXISTS telemetry_readings (
    id SERIAL PRIMARY KEY,
    node_id TEXT NOT NULL,
    timestamp BIGINT NOT NULL,
    voltage DOUBLE PRECISION NOT NULL,
    current DOUBLE PRECISION NOT NULL,
    power DOUBLE PRECISION NOT NULL,
    energy_wh DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (node_id, timestamp)
);

CREATE TABLE IF NOT EXISTS node_events (
    id SERIAL PRIMARY KEY,
    node_id TEXT NOT NULL,
    node_type TEXT,
    timestamp BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    message TEXT NOT NULL,
    buffered BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS node_health (
    id SERIAL PRIMARY KEY,
    node_id TEXT NOT NULL,
    node_type TEXT,
    timestamp BIGINT NOT NULL,
    sequence_no INTEGER,
    status TEXT,
    uptime_sec INTEGER,
    mqtt_connected BOOLEAN,
    wifi_connected BOOLEAN,
    sensor_ok BOOLEAN,
    buffered_count INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS node_metadata (
    node_id TEXT PRIMARY KEY,
    node_type TEXT NOT NULL,
    location TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS anomaly_records (
    id SERIAL PRIMARY KEY,
    node_id TEXT NOT NULL,
    timestamp BIGINT NOT NULL,
    anomaly_type TEXT NOT NULL,
    score DOUBLE PRECISION NOT NULL,
    severity TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS forecasts (
    id SERIAL PRIMARY KEY,
    node_id TEXT NOT NULL,
    timestamp BIGINT NOT NULL,
    predicted_consumption DOUBLE PRECISION NOT NULL
);
