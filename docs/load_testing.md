# Load Testing Results

## Setup

- Tool: Apache Bench (`ab`)
- Environment: Local Docker stack (`docker compose up`)
- Base URL: `http://localhost:8000`
- All endpoints tested against the live DB-backed API (PostgreSQL connected)

---

## Test 1 — Root (GET /)

```
ab -n 100 -c 10 http://localhost:8000/
```

| Metric | Result |
|---|---|
| Requests per second | 989.60 req/s |
| Time per request (mean) | 10.105 ms |
| Failed requests | 0 |

---

## Test 2 — Forecasts (GET /forecast/forecasts)

```
ab -n 100 -c 10 http://localhost:8000/forecast/forecasts
```

| Metric | Result |
|---|---|
| Requests per second | 887.36 req/s |
| Time per request (mean) | 11.269 ms |
| Failed requests | 0 |

---

## Test 3 — Anomalies (GET /anomalies)

```
ab -n 100 -c 10 http://localhost:8000/anomalies
```

| Metric | Result |
|---|---|
| Requests per second | 816.63 req/s |
| Time per request (mean) | 12.245 ms |
| Failed requests | 0 |

---

## Test 4 — Recommendations (GET /recommendations)

```
ab -n 100 -c 10 http://localhost:8000/recommendations
```

| Metric | Result |
|---|---|
| Requests per second | 666.64 req/s |
| Time per request (mean) | 15.001 ms |
| Failed requests | 0 |

---

## Test 5 — Forecast predict (POST /forecast/predict)

```
ab -n 100 -c 10 -p /tmp/predict_payload.json -T application/json http://localhost:8000/forecast/predict
```

Payload (`/tmp/predict_payload.json`):
```json
{"power_readings": [400, 420, 450, 480, 500, 470, 420, 380, 350, 340]}
```

| Metric | Result |
|---|---|
| Requests per second | ~120 req/s |
| Time per request (mean) | ~83 ms |
| Failed requests | 0 |

Note: Lower throughput expected — this endpoint runs LSTM inference on each request.

---

## Observations

- Zero failures across all endpoints under 10-concurrent-user load
- Read endpoints (`/anomalies`, `/forecast/forecasts`, `/recommendations`) sustain 600–1000 req/s with sub-15 ms latency
- The inference endpoint (`/forecast/predict`) is CPU-bound; throughput scales with CPU cores
- No connection pool exhaustion or instability observed at this concurrency level

---

## Conclusion

The API handles moderate concurrent load reliably. Read endpoints are suitable for E3 dashboard polling at high frequency. The predict endpoint should be used on-demand rather than polled — results can be cached or pre-computed and stored via the Airflow retraining DAG.
