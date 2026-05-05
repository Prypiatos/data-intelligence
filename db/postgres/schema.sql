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

CREATE TABLE IF NOT EXISTS stream_summaries (
    id SERIAL PRIMARY KEY,
    node_id TEXT NOT NULL,
    window_start BIGINT NOT NULL,
    window_end BIGINT NOT NULL,
    avg_power DOUBLE PRECISION NOT NULL,
    max_power DOUBLE PRECISION NOT NULL,
    record_count INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (node_id, window_start)
);

CREATE TABLE IF NOT EXISTS forecasts (
    id SERIAL PRIMARY KEY,
    node_id TEXT NOT NULL,
    timestamp BIGINT NOT NULL,
    predicted_consumption DOUBLE PRECISION NOT NULL
);
CREATE TABLE IF NOT EXISTS energy_features (
    id SERIAL PRIMARY KEY,
    node_id TEXT NOT NULL,
    timestamp BIGINT NOT NULL,
    avg_power DOUBLE PRECISION,
    avg_voltage DOUBLE PRECISION,
    avg_current DOUBLE PRECISION,
    min_power DOUBLE PRECISION,
    max_power DOUBLE PRECISION,
    std_power DOUBLE PRECISION,
    avg_energy_wh DOUBLE PRECISION,
    reading_count INTEGER,
    hour INTEGER,
    day_of_week INTEGER,
    day_of_month INTEGER,
    lag_1h DOUBLE PRECISION,
    lag_24h DOUBLE PRECISION,
    lag_168h DOUBLE PRECISION,
    rolling_avg_1d DOUBLE PRECISION,
    rolling_avg_7d DOUBLE PRECISION,
    rolling_avg_30d DOUBLE PRECISION,
    rolling_min_24h DOUBLE PRECISION,
    rolling_max_24h DOUBLE PRECISION,
    rolling_std_24h DOUBLE PRECISION,
    created_at TIMESTAMP DEFAULT NOW(),
    pipeline_version VARCHAR(20),
    aggregation_level VARCHAR(20),
    UNIQUE(node_id, timestamp)
);

CREATE INDEX idx_energy_features_node_timestamp 
ON energy_features(node_id, timestamp);

CREATE TABLE IF NOT EXISTS energy_analytics_hourly (
    id SERIAL PRIMARY KEY,
    node_id TEXT NOT NULL,
    division TEXT,
    hour_start TIMESTAMP NOT NULL,
    total_consumption_wh DOUBLE PRECISION NOT NULL,
    avg_power_w DOUBLE PRECISION,
    peak_power_w DOUBLE PRECISION,
    reading_count INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (node_id, hour_start)
);

CREATE TABLE IF NOT EXISTS energy_analytics_daily (
    id SERIAL PRIMARY KEY,
    node_id TEXT NOT NULL,
    division TEXT,
    date DATE NOT NULL,
    total_consumption_wh DOUBLE PRECISION NOT NULL,
    avg_power_w DOUBLE PRECISION,
    peak_power_w DOUBLE PRECISION,
    reading_count INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (node_id, date)
);
