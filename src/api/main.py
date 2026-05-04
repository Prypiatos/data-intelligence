"""
FastAPI application for the Energy Management System - E2 Data & Intelligence.

This is the main entry point that combines routes from all E2 sub-teams
(forecasting, ingestion, streaming, etc.) into a single unified API.

Architecture:
- main.py: Entry point, combines all routes
- routes/forecasting.py: Forecasting endpoints (your code)
- routes/health.py: Health check endpoints (basic monitoring)
- routes/: Other teams add their modules here without conflicts
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import route modules from other teams
from src.api.routes import anomalies, forecasting, health, recommendations


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("\n" + "=" * 80)
    print("Energy Management System API Startup")
    print("=" * 80)

    forecasting.initialize_forecasting()

    print("\nAll systems initialized successfully!")
    print("=" * 80 + "\n")

    yield

    print("\nEnergy Management System API Shutting Down\n")


# ============================================
# Create FastAPI Application
# ============================================

app = FastAPI(
    title="Energy Management System API",
    description="API for the E2 Data & Intelligence team - Forecasting, ingestion, streaming, and more",
    version="1.0.0",
    contact={"name": "E2 Data & Intelligence Team", "email": "e2@prypiatos.com"},
    lifespan=lifespan,
)

# ============================================
# CORS Configuration
# ============================================

_cors_origins = os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
_allow_origins = [o.strip() for o in _cors_origins if o.strip()] or ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# Include Route Modules
# ============================================

# Each route module adds its endpoints to this app
# This is where multiple teams combine their work
app.include_router(health.router)
app.include_router(forecasting.router)
app.include_router(anomalies.router)
app.include_router(recommendations.router)

# When Person 4 creates their API infrastructure routes, they'll add:
# app.include_router(api_routes.router)
# When Person 2 creates ingestion routes:
# app.include_router(ingestion.router)
# And so on - all without modifying this file!

# ============================================
# Root Endpoint
# ============================================


@app.get("/")
def root():
    return {
        "name": "Energy Management System API",
        "version": "1.0.0",
        "team": "E2 Data & Intelligence",
        "endpoints": {
            "health": "/health (GET)",
            "forecasts": "/forecast/forecasts (GET)",
            "forecast_predict": "/forecast/predict (POST)",
            "forecast_batch": "/forecast/predict-batch (POST)",
            "anomalies": "/anomalies (GET)",
            "recommendations": "/recommendations (GET)",
            "documentation": "/docs (GET)",
        },
        "docs_url": "/docs",
    }


# ============================================
# Entry Point
# ============================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
