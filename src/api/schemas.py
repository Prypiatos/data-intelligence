from pydantic import BaseModel
from typing import List, Optional


# Base response structure (common for all endpoints)
class BaseResponse(BaseModel):
    status: str
    message: Optional[str] = None


# Root message response
class MessageData(BaseModel):
    message: str


class MessageResponse(BaseResponse):
    data: MessageData


# Forecast schemas
class ForecastItem(BaseModel):
    time: str
    value: float


class ForecastData(BaseModel):
    node_id: int
    forecast: List[ForecastItem]


class ForecastResponse(BaseResponse):
    data: ForecastData


# Anomaly schemas
class AnomalyData(BaseModel):
    node_id: int
    status: str
    score: float


class AnomalyResponse(BaseResponse):
    data: AnomalyData


# Recommendation schemas
class RecommendationData(BaseModel):
    node_id: int
    actions: List[str]


class RecommendationResponse(BaseResponse):
    data: RecommendationData
