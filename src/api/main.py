from fastapi import FastAPI
from src.api.schemas import (
    MessageResponse,
    ForecastResponse,
    AnomalyResponse,
    RecommendationResponse,
)

app = FastAPI()


@app.get("/", response_model=MessageResponse)
def root():
    return {"message": "API running"}


@app.get("/forecasts", response_model=ForecastResponse)
def get_forecasts():
    return {
        "node_id": 1,
        "forecast": [{"time": "10:00", "value": 120}, {"time": "11:00", "value": 135}],
    }


@app.get("/anomalies", response_model=AnomalyResponse)
def get_anomalies():
    return {"node_id": 1, "status": "normal", "score": 0.1}


@app.get("/recommendations", response_model=RecommendationResponse)
def get_recommendations():
    return {"node_id": 1, "actions": ["Reduce peak usage", "Check equipment"]}
