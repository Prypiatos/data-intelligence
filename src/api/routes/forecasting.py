"""
Forecasting endpoints for LSTM load prediction model.

This module provides HTTP endpoints for making 24-hour energy consumption
forecasts using the trained LSTM neural network model.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import torch
import numpy as np
import os
from typing import List

from src.models.forecasting.lstm_model import LSTMForecaster
from sklearn.preprocessing import MinMaxScaler

# Create a router for forecasting endpoints
router = APIRouter(prefix="/forecast", tags=["forecasting"])

# Global variables to hold the model and scaler (loaded once at startup)
# Using global variables here is fine because the model doesn't change during runtime
model = None
device = None
scaler = None

# ============================================
# Request and Response Models
# ============================================

class PredictionRequest(BaseModel):
    """Request model for single prediction."""
    power_readings: List[float]  # Last 10 hours of power readings in watts
    
    class Config:
        # This example shows clients what format to send
        example = {
            "power_readings": [400, 420, 450, 480, 500, 470, 420, 380, 350, 340]
        }


class PredictionResponse(BaseModel):
    """Response model for single prediction."""
    forecast: List[float]  # 24-hour forecast in watts
    hours_ahead: int  # How many hours ahead (always 24)
    unit: str  # Unit of measurement (always "watts")
    
    class Config:
        example = {
            "forecast": [420, 440, 460, 480, 500, 490, 470, 450, 430, 410],
            "hours_ahead": 24,
            "unit": "watts"
        }


class BatchPredictionRequest(BaseModel):
    """Request model for batch predictions."""
    batch_readings: List[List[float]]  # Multiple sequences of 10 readings each
    
    class Config:
        example = {
            "batch_readings": [
                [400, 420, 450, 480, 500, 470, 420, 380, 350, 340],
                [410, 430, 460, 490, 510, 480, 430, 390, 360, 350]
            ]
        }


class BatchPredictionResponse(BaseModel):
    """Response model for batch predictions."""
    forecasts: List[List[float]]  # Multiple 24-hour forecasts
    count: int  # Number of forecasts returned


# ============================================
# Initialization Function
# ============================================

def initialize_forecasting():
    """
    Initialize the forecasting model.
    
    This function is called once when the API starts up. It loads the trained
    LSTM model from disk and initializes the scaler for normalizing input data.
    
    This separation (loading in a function rather than at module import time)
    is important because it allows the API to start even if the model file is
    temporarily missing, which is useful for debugging and testing.
    """
    global model, device, scaler
    
    print("🚀 Initializing forecasting model...")
    
    try:
        # Determine if GPU is available
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        print(f"   Device: {device}")
        
        # Create model with the same architecture used during training
        model = LSTMForecaster()
        model = model.to(device)
        
        # Load trained weights from disk
        model_path = "models/lstm_model.pth"
        if os.path.exists(model_path):
            # map_location ensures the model loads correctly whether it was
            # trained on GPU or CPU, and whether we're now on GPU or CPU
            model.load_state_dict(torch.load(model_path, map_location=device))
            print(f"   ✅ Model loaded from {model_path}")
        else:
            print(f"   ⚠️  Model file not found at {model_path}")
            print(f"   API will use untrained model (predictions won't be accurate)")
        
        # Set model to evaluation mode
        # This disables dropout and other training-specific behaviors
        model.eval()
        
        # Initialize scaler for normalizing input data
        # We normalize to 0-1 range, with 0W and 800W as the bounds
        scaler = MinMaxScaler()
        scaler.fit([[0], [800]])
        print(f"   ✅ Scaler initialized")
        
        print("✅ Forecasting model ready!")
        
    except Exception as e:
        print(f"❌ Error initializing forecasting model: {str(e)}")
        print(f"   The API will continue running but predictions won't work")
        # We don't raise an exception here because we want the API to start
        # even if model loading fails. This is useful for debugging.


# ============================================
# Endpoint: Single Prediction
# ============================================

@router.post("/predict", response_model=PredictionResponse)
def predict(request: PredictionRequest):
    """
    Make a single 24-hour forecast.
    
    This endpoint takes 10 hours of historical power readings and returns
    a forecast for the next 24 hours.
    
    Args:
        request: Contains list of 10 power readings (last 10 hours)
        
    Returns:
        PredictionResponse with 24-hour forecast
        
    Raises:
        HTTPException: If model not loaded or input is invalid
    """
    # First check: is the model loaded?
    if model is None:
        raise HTTPException(
            status_code=503,  # Service Unavailable
            detail="Model not loaded. Try again in a moment."
        )
    
    try:
        # Validate input length
        if len(request.power_readings) != 10:
            raise HTTPException(
                status_code=400,  # Bad Request
                detail=f"Expected 10 power readings, got {len(request.power_readings)}"
            )
        
        # Normalize input to 0-1 range (same as training)
        # The model was trained on normalized data, so we must normalize input
        readings_array = np.array(request.power_readings).reshape(-1, 1)
        normalized = scaler.transform(readings_array)
        
        # Convert to PyTorch tensor with correct shape
        # Shape should be (batch_size=1, sequence_length=10, features=1)
        X = torch.FloatTensor(normalized).unsqueeze(0).to(device)
        
        # Make prediction
        # We use torch.no_grad() because we're not training, just inferring
        # This saves memory and makes inference faster
        with torch.no_grad():
            output = model(X)  # Output shape: (1, 24)
        
        # Convert back to numpy and denormalize to get actual watts
        forecast_normalized = output.cpu().numpy()[0]
        forecast = scaler.inverse_transform(
            forecast_normalized.reshape(-1, 1)
        ).flatten()
        
        # Ensure no negative predictions (power can't be negative)
        forecast = np.maximum(forecast, 0)
        
        return PredictionResponse(
            forecast=forecast.tolist(),
            hours_ahead=24,
            unit="watts"
        )
    
    except HTTPException:
        # Re-raise HTTP exceptions (our validation errors)
        raise
    except Exception as e:
        # Catch unexpected errors and return 500
        raise HTTPException(
            status_code=500,  # Internal Server Error
            detail=f"Prediction error: {str(e)}"
        )


# ============================================
# Endpoint: Batch Prediction
# ============================================

@router.post("/predict-batch", response_model=BatchPredictionResponse)
def predict_batch(request: BatchPredictionRequest):
    """
    Make multiple 24-hour forecasts at once.
    
    Useful when you need forecasts for multiple time periods or locations
    in a single request, rather than making multiple /predict calls.
    
    Args:
        request: Contains list of sequences, each with 10 power readings
        
    Returns:
        BatchPredictionResponse with multiple forecasts
        
    Raises:
        HTTPException: If model not loaded or input is invalid
    """
    if model is None:
        raise HTTPException(
            status_code=503,
            detail="Model not loaded. Try again in a moment."
        )
    
    try:
        if not request.batch_readings:
            raise HTTPException(
                status_code=400,
                detail="Empty batch - provide at least one sequence"
            )
        
        batch_size = len(request.batch_readings)
        forecasts = []
        
        # Process each sequence in the batch
        for readings in request.batch_readings:
            if len(readings) != 10:
                raise HTTPException(
                    status_code=400,
                    detail=f"Expected 10 readings per sequence, got {len(readings)}"
                )
            
            # Same process as single prediction
            readings_array = np.array(readings).reshape(-1, 1)
            normalized = scaler.transform(readings_array)
            X = torch.FloatTensor(normalized).unsqueeze(0).to(device)
            
            with torch.no_grad():
                output = model(X)
            
            forecast_normalized = output.cpu().numpy()[0]
            forecast = scaler.inverse_transform(
                forecast_normalized.reshape(-1, 1)
            ).flatten()
            forecast = np.maximum(forecast, 0)
            
            forecasts.append(forecast.tolist())
        
        return BatchPredictionResponse(
            forecasts=forecasts,
            count=batch_size
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Batch prediction error: {str(e)}"
        )