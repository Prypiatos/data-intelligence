# Load Testing Results

## Setup

* Tool: Apache Bench (ab)
* Environment: Local (FastAPI)
* Base URL: http://localhost:8000

---

## Test 1 — Root (/)

Command:
ab -n 100 -c 10 http://localhost:8000/

Results:

* Requests per second: 989.60 [#/sec]
* Time per request: 10.105 ms
* Failed requests: 0

---

## Test 2 — Forecasts (/forecasts)

Command:
ab -n 100 -c 10 http://localhost:8000/forecasts

Results:

* Requests per second: 887.36 [#/sec]
* Time per request: 11.269 ms
* Failed requests: 0

---

## Test 3 — Anomalies (/anomalies)

Command:
ab -n 100 -c 10 http://localhost:8000/anomalies

Results:

* Requests per second: 816.63 [#/sec]
* Time per request: 12.245 ms
* Failed requests: 0

---

## Test 4 — Recommendations (/recommendations)

Command:
ab -n 100 -c 10 http://localhost:8000/recommendations

Results:

* Requests per second: 666.64 [#/sec]
* Time per request: 15.001 ms
* Failed requests: 0

---

## Observations

* All endpoints handled concurrent requests successfully with zero failures
* Performance decreases slightly as response complexity increases
* Response times remain low (10–15 ms) across all endpoints
* Throughput remains high (600–1000 requests/sec)
* No bottlenecks or instability observed

---

## Conclusion

The API performs reliably under moderate load conditions.
All endpoints demonstrate stable performance, low latency, and high throughput.

The system is ready for integration with other services.
