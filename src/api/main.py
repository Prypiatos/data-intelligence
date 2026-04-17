from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"message": "API running"}

@app.get("/forecasts")
def get_forecasts():
    return {
        "node_id": 1,
        "forecast": [
            {"time": "10:00", "value": 120},
            {"time": "11:00", "value": 135}
        ]
    }


@app.get("/anomalies")
def get_anomalies():
    return {
        "node_id": 1,
        "status": "normal",
        "score": 0.1
    }


@app.get("/recommendations")
def get_recommendations():
    return {
        "node_id": 1,
        "actions": [
            "Reduce peak usage",
            "Check equipment"
        ]
    }