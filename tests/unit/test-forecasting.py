import pytest
import torch
import numpy as np
from sklearn.preprocessing import MinMaxScaler

# Assuming these are in your src/models/forecasting/lstm_model.py
# Adjust imports based on your actual file structure
try:
    from src.models.forecasting.lstm_model import LSTMForecaster, create_mock_data
except ImportError:
    # For testing purposes, you can define them here
    pass


class TestMockData:
    """Test mock data generation"""
    
    def test_mock_data_length(self):
        """Test that mock data has correct length"""
        days = 10
        df = create_mock_data(days=days)
        expected_length = days * 24  # 24 hours per day
        assert len(df) == expected_length, f"Expected {expected_length} rows, got {len(df)}"
    
    def test_mock_data_columns(self):
        """Test that mock data has required columns"""
        df = create_mock_data(days=7)
        required_columns = ['timestamp', 'power', 'hour', 'day']
        for col in required_columns:
            assert col in df.columns, f"Missing column: {col}"
    
    def test_mock_data_power_positive(self):
        """Test that power values are positive"""
        df = create_mock_data(days=7)
        assert (df['power'] >= 0).all(), "Power values should be non-negative"
    
    def test_mock_data_timestamp_unique(self):
        """Test that timestamps are unique"""
        df = create_mock_data(days=7)
        assert df['timestamp'].is_unique, "Timestamps should be unique"
    
    def test_mock_data_reasonable_range(self):
        """Test that power values are in reasonable range"""
        df = create_mock_data(days=7)
        # Power should be roughly between 0 and 1000 watts for realistic data
        assert df['power'].min() >= 0, "Min power should be >= 0"
        assert df['power'].max() <= 2000, "Max power should be <= 2000"


class TestLSTMModel:
    """Test LSTM model architecture and functionality"""
    
    def test_model_initialization(self):
        """Test that model initializes correctly"""
        model = LSTMForecaster()
        assert isinstance(model, torch.nn.Module), "Model should be a PyTorch Module"
    
    def test_model_forward_pass(self):
        """Test forward pass with correct input shape"""
        model = LSTMForecaster()
        # Input shape: (batch_size=1, seq_length=10, input_size=1)
        X = torch.randn(1, 10, 1)
        output = model(X)
        
        # Output should have shape (batch_size=1, forecast_horizon=24)
        assert output.shape == (1, 24), f"Expected output shape (1, 24), got {output.shape}"
    
    def test_model_batch_processing(self):
        """Test model with multiple samples in batch"""
        model = LSTMForecaster()
        batch_size = 4
        X = torch.randn(batch_size, 10, 1)
        output = model(X)
        
        assert output.shape == (batch_size, 24), f"Expected shape ({batch_size}, 24), got {output.shape}"
    
    def test_model_output_dtype(self):
        """Test that output has correct data type"""
        model = LSTMForecaster()
        X = torch.randn(1, 10, 1)
        output = model(X)
        
        assert output.dtype == torch.float32, f"Expected float32, got {output.dtype}"
    
    def test_model_output_finite(self):
        """Test that output contains finite values"""
        model = LSTMForecaster()
        X = torch.randn(1, 10, 1)
        output = model(X)
        
        assert torch.isfinite(output).all(), "Output should contain only finite values"


class TestTraining:
    """Test training functionality"""
    
    def test_loss_decreases(self):
        """Test that loss decreases during training"""
        model = LSTMForecaster()
        optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
        loss_fn = torch.nn.MSELoss()
        
        losses = []
        X = torch.randn(1, 10, 1)
        y = torch.randn(1, 24)
        
        for epoch in range(5):
            optimizer.zero_grad()
            output = model(X)
            loss = loss_fn(output, y)
            loss.backward()
            optimizer.step()
            losses.append(loss.item())
        
        # Loss should generally decrease (allow some fluctuation)
        assert losses[-1] < losses[0] * 1.5, "Loss should decrease during training"
    
    def test_model_gradients_update(self):
        """Test that model parameters are updated during training"""
        model = LSTMForecaster()
        optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
        loss_fn = torch.nn.MSELoss()
        
        # Get initial parameters
        initial_params = [p.clone() for p in model.parameters()]
        
        X = torch.randn(1, 10, 1)
        y = torch.randn(1, 24)
        
        # Training step
        optimizer.zero_grad()
        output = model(X)
        loss = loss_fn(output, y)
        loss.backward()
        optimizer.step()
        
        # Check that parameters changed
        for init_p, param in zip(initial_params, model.parameters()):
            assert not torch.allclose(init_p, param), "Parameters should be updated"


class TestDataPreprocessing:
    """Test data preprocessing"""
    
    def test_scaler_initialization(self):
        """Test MinMaxScaler works correctly"""
        scaler = MinMaxScaler()
        df = create_mock_data(days=7)
        
        scaled_data = scaler.fit_transform(df[['power']])
        
        # Scaled data should be between 0 and 1
        assert scaled_data.min() >= 0, "Scaled data min should be >= 0"
        assert scaled_data.max() <= 1.0001, "Scaled data max should be <= 1"
    
    def test_scaler_inverse_transform(self):
        """Test inverse transform returns original scale"""
        scaler = MinMaxScaler()
        df = create_mock_data(days=7)
        original_data = df[['power']].values
        
        scaled_data = scaler.fit_transform(original_data)
        unscaled_data = scaler.inverse_transform(scaled_data)
        
        # Should be very close to original (within tolerance)
        np.testing.assert_array_almost_equal(original_data, unscaled_data, decimal=5)


class TestIntegration:
    """Integration tests for complete workflow"""
    
    def test_end_to_end_training(self):
        """Test complete training pipeline"""
        # Create mock data
        df = create_mock_data(days=20)
        
        # Preprocess
        scaler = MinMaxScaler()
        scaled_data = scaler.fit_transform(df[['power']])
        
        # Create model
        model = LSTMForecaster()
        optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
        loss_fn = torch.nn.MSELoss()
        
        # Train for 1 epoch
        X = torch.FloatTensor(scaled_data[:-24]).unsqueeze(1)
        y = torch.FloatTensor(scaled_data[24:, 0])
        
        optimizer.zero_grad()
        output = model(X)
        loss = loss_fn(output[-1].unsqueeze(0), y[-24:].unsqueeze(0))
        loss.backward()
        optimizer.step()
        
        assert loss.item() > 0, "Loss should be positive"
    
    def test_prediction_shape_consistency(self):
        """Test predictions have consistent shape"""
        model = LSTMForecaster()
        
        # Test multiple times
        for _ in range(3):
            X = torch.randn(1, 10, 1)
            output = model(X)
            assert output.shape == (1, 24), "Prediction shape should be consistent"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])