from pydantic import BaseModel
from typing import List


class MessageResponse(BaseModel):
    message: str


class ForecastItem(BaseModel):
    time: str
    value: float


class ForecastResponse(BaseModel):
    node_id: int
    forecast: List[ForecastItem]


class AnomalyResponse(BaseModel):
    node_id: int
    status: str
    score: float


class RecommendationResponse(BaseModel):
    node_id: int
    actions: List[str]
