"""
Health check endpoints for the API.

These endpoints allow monitoring systems and load balancers to verify
that the forecasting service is running and responsive.
"""

from fastapi import APIRouter
from pydantic import BaseModel

# Create a router for health endpoints
# APIRouter is like a mini FastAPI app that handles related endpoints
# prefix="/health" means all routes in this router will start with /health
# tags=["health"] is for organizing in the API documentation
router = APIRouter(prefix="/health", tags=["health"])

# Define the response model so clients know what to expect
class HealthResponse(BaseModel):
    """Response from health check endpoint."""
    status: str  # "healthy" or "unhealthy"
    version: str  # API version
    service: str  # Name of the service

# Define the health check endpoint
@router.get("")
def health_check():
    """
    Health check endpoint.
    
    Returns the current status of the API. Monitoring systems call this
    regularly to detect if the service has crashed or is unresponsive.
    
    Returns:
        HealthResponse with status and version info
    """
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        service="Load Forecasting API"
    )