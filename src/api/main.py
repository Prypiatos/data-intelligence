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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import route modules from other teams
from src.api.routes import forecasting, health

# ============================================
# Create FastAPI Application
# ============================================

app = FastAPI(
    title="Energy Management System API",
    description="API for the E2 Data & Intelligence team - Forecasting, ingestion, streaming, and more",
    version="1.0.0",
    contact={
        "name": "E2 Data & Intelligence Team",
        "email": "e2@prypiatos.com"
    }
)

# ============================================
# CORS Configuration
# ============================================

# Allow other teams (E1, E3, E4) to call our API from different domains
# CORS = Cross-Origin Resource Sharing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific domains
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
    """
    Root endpoint with API information.
    
    Returns basic information about the API and links to documentation.
    """
    return {
        "name": "Energy Management System API",
        "version": "1.0.0",
        "team": "E2 Data & Intelligence",
        "endpoints": {
            "health": "/health (GET)",
            "forecast": "/forecast/predict (POST)",
            "forecast_batch": "/forecast/predict-batch (POST)",
            "documentation": "/docs (GET)"
        },
        "docs_url": "/docs"
    }

# ============================================
# Startup and Shutdown Events
# ============================================

@app.on_event("startup")
async def startup_event():
    """
    Run when the API starts up.
    
    Initialize all modules and load models. This runs once when the
    Docker container starts, not on every request.
    """
    print("\n" + "="*80)
    print("🚀 Energy Management System API Startup")
    print("="*80)
    
    # Initialize forecasting model
    # This calls the initialize_forecasting function in forecasting.py
    forecasting.initialize_forecasting()
    
    print("\n✅ All systems initialized successfully!")
    print("="*80 + "\n")


@app.on_event("shutdown")
async def shutdown_event():
    """Run when the API shuts down (cleanup)."""
    print("\n🛑 Energy Management System API Shutting Down\n")


# ============================================
# Entry Point
# ============================================

if __name__ == "__main__":
    # This allows running the app directly: python src/api/main.py
    import uvicorn
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )