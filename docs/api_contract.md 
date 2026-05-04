# API Contract

## Base URL

http://localhost:8000

---

## Standard Response Format

All endpoints return:

```json
{
  "status": "success",
  "data": {},
  "message": null
}
```

---

## Endpoints

### GET /

**Description:** Check API status

**Response:**

```json
{
  "status": "success",
  "data": {
    "message": "API running"
  },
  "message": "OK"
}
```

---

### GET /forecasts

**Description:** Get forecast data for a node

**Response:**

```json
{
  "status": "success",
  "data": {
    "node_id": 1,
    "forecast": [
      {"time": "10:00", "value": 120},
      {"time": "11:00", "value": 135}
    ]
  },
  "message": "Forecast data retrieved"
}
```

---

### GET /anomalies

**Description:** Get anomaly status for a node

**Response:**

```json
{
  "status": "success",
  "data": {
    "node_id": 1,
    "status": "normal",
    "score": 0.1
  },
  "message": "Anomaly status retrieved"
}
```

---

### GET /recommendations

**Description:** Get recommendations for a node

**Response:**

```json
{
  "status": "success",
  "data": {
    "node_id": 1,
    "actions": [
      "Reduce peak usage",
      "Check equipment"
    ]
  },
  "message": "Recommendations retrieved"
}
```

---

## Swagger Documentation

Interactive API documentation is available at:

http://localhost:8000/docs

---

## Notes

* All responses follow a standardized format (`status`, `data`, `message`)
* Response schemas are defined using Pydantic models
* Endpoints are ready for integration with E3 (dashboard) and E4 (platform/gateway)
