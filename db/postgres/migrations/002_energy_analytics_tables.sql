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
