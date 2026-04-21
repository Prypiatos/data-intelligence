# Start MLflow
mlflow server --host 0.0.0.0 --port 5000

# View dashboard
open http://localhost:5000

# Search experiments
mlflow experiments list

# Search runs
mlflow runs list

# View run details
mlflow runs describe <RUN_ID>

# Download artifacts
mlflow artifacts download <RUN_ID> -d ./artifacts

# Clean up
mlflow gc  # Garbage collection