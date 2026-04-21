"""
MLflow Setup and Configuration
Task #15: MLflow Experiment Tracking Setup

This module provides utilities for initializing and managing MLflow experiments.
"""

import os
import mlflow
from typing import Dict, List, Optional


class MLflowSetup:
    """Initialize and configure MLflow for experiment tracking."""

    def __init__(self, tracking_uri: str = "http://localhost:5000"):
        """
        Initialize MLflow setup.

        Args:
            tracking_uri: MLflow server URI
        """
        self.tracking_uri = tracking_uri
        mlflow.set_tracking_uri(tracking_uri)

    def create_experiments(self) -> Dict[str, str]:
        """
        Create required experiments for Task #15.

        Returns:
            Dictionary with experiment names and IDs
        """
        experiments = {}

        # Load Forecasting Experiment
        try:
            load_forecasting_exp = mlflow.create_experiment(
                name="load-forecasting",
                artifact_location="./mlflow/artifacts/load-forecasting",
            )
            experiments["load-forecasting"] = load_forecasting_exp
            print(
                f"✅ Created 'load-forecasting' experiment (ID: {load_forecasting_exp})"
            )
        except Exception as e:
            # Experiment might already exist
            exp = mlflow.get_experiment_by_name("load-forecasting")
            if exp:
                experiments["load-forecasting"] = exp.experiment_id
                print(
                    f"ℹ️  'load-forecasting' experiment already exists (ID: {exp.experiment_id})"
                )
            else:
                print(f"❌ Error creating 'load-forecasting': {str(e)}")

        # Anomaly Detection Experiment
        try:
            anomaly_exp = mlflow.create_experiment(
                name="anomaly-detection",
                artifact_location="./mlflow/artifacts/anomaly-detection",
            )
            experiments["anomaly-detection"] = anomaly_exp
            print(f"✅ Created 'anomaly-detection' experiment (ID: {anomaly_exp})")
        except Exception as e:
            # Experiment might already exist
            exp = mlflow.get_experiment_by_name("anomaly-detection")
            if exp:
                experiments["anomaly-detection"] = exp.experiment_id
                print(
                    f"ℹ️  'anomaly-detection' experiment already exists (ID: {exp.experiment_id})"
                )
            else:
                print(f"❌ Error creating 'anomaly-detection': {str(e)}")

        return experiments

    def set_experiment(self, experiment_name: str) -> None:
        """
        Set active experiment.

        Args:
            experiment_name: Name of experiment to activate
        """
        mlflow.set_experiment(experiment_name)
        print(f"✅ Set active experiment: {experiment_name}")

    @staticmethod
    def log_forecast_run(
        run_name: str,
        params: Dict,
        metrics: Dict,
        artifacts: Optional[List[str]] = None,
        tags: Optional[Dict] = None,
    ) -> str:
        """
        Log a load forecasting run to MLflow.

        Args:
            run_name: Name for this run
            params: Dictionary of hyperparameters
            metrics: Dictionary of metrics
            artifacts: List of artifact file paths
            tags: Dictionary of tags

        Returns:
            Run ID
        """
        with mlflow.start_run(run_name=run_name):
            # Log parameters
            for param_name, param_value in params.items():
                mlflow.log_param(param_name, param_value)

            # Log metrics
            for metric_name, metric_value in metrics.items():
                mlflow.log_metric(metric_name, metric_value)

            # Log artifacts
            if artifacts:
                for artifact_path in artifacts:
                    if os.path.exists(artifact_path):
                        mlflow.log_artifact(artifact_path)
                    else:
                        print(f"⚠️  Artifact not found: {artifact_path}")

            # Log tags
            if tags:
                mlflow.set_tags(tags)

            # Default tags
            mlflow.set_tags(
                {
                    "component": "forecasting",
                    "team": "E2",
                    "model_family": "lstm",
                }
            )

            run_id = mlflow.active_run().info.run_id
            print(f"✅ Logged forecast run: {run_id}")
            return run_id

    @staticmethod
    def log_anomaly_run(
        run_name: str,
        params: Dict,
        metrics: Dict,
        artifacts: Optional[List[str]] = None,
        tags: Optional[Dict] = None,
    ) -> str:
        """
        Log an anomaly detection run to MLflow.

        Args:
            run_name: Name for this run
            params: Dictionary of hyperparameters
            metrics: Dictionary of metrics
            artifacts: List of artifact file paths
            tags: Dictionary of tags

        Returns:
            Run ID
        """
        with mlflow.start_run(run_name=run_name):
            # Log parameters
            for param_name, param_value in params.items():
                mlflow.log_param(param_name, param_value)

            # Log metrics
            for metric_name, metric_value in metrics.items():
                mlflow.log_metric(metric_name, metric_value)

            # Log artifacts
            if artifacts:
                for artifact_path in artifacts:
                    if os.path.exists(artifact_path):
                        mlflow.log_artifact(artifact_path)
                    else:
                        print(f"⚠️  Artifact not found: {artifact_path}")

            # Log tags
            if tags:
                mlflow.set_tags(tags)

            # Default tags
            mlflow.set_tags(
                {
                    "component": "anomaly_detection",
                    "team": "E2",
                    "model_family": "isolation_forest",
                }
            )

            run_id = mlflow.active_run().info.run_id
            print(f"✅ Logged anomaly detection run: {run_id}")
            return run_id

    @staticmethod
    def compare_runs(experiment_name: str, sort_by: str = "metrics.mape ASC") -> None:
        """
        Compare all runs in an experiment.

        Args:
            experiment_name: Name of experiment to compare
            sort_by: Sort criteria (e.g., "metrics.mape ASC")
        """
        try:
            experiment = mlflow.get_experiment_by_name(experiment_name)
            if not experiment:
                print(f"❌ Experiment not found: {experiment_name}")
                return

            # Search runs
            runs = mlflow.search_runs(
                experiment_ids=[experiment.experiment_id], order_by=[sort_by]
            )

            if runs.empty:
                print(f"ℹ️  No runs found in '{experiment_name}'")
                return

            print(f"\n📊 Comparison of runs in '{experiment_name}':")
            print("=" * 80)

            # Display runs
            for idx, run in runs.iterrows():
                print(f"\nRun {idx + 1}:")
                print(f"  ID: {run['run_id']}")
                print(f"  Name: {run.get('tags.mlflow.runName', 'N/A')}")

                # Print metrics
                metric_cols = [
                    col for col in runs.columns if col.startswith("metrics.")
                ]
                if metric_cols:
                    print("  Metrics:")
                    for metric_col in metric_cols:
                        value = run[metric_col]
                        metric_name = metric_col.replace("metrics.", "")
                        print(f"    {metric_name}: {value}")

        except Exception as e:
            print(f"❌ Error comparing runs: {str(e)}")

    @staticmethod
    def list_experiments() -> None:
        """List all experiments."""
        try:
            experiments = mlflow.search_experiments()

            if not experiments:
                print("ℹ️  No experiments found")
                return

            print("\n📋 Available Experiments:")
            print("=" * 80)

            for exp in experiments:
                print(f"\n{exp.name}")
                print(f"  ID: {exp.experiment_id}")
                print(f"  Artifact Location: {exp.artifact_location}")

        except Exception as e:
            print(f"❌ Error listing experiments: {str(e)}")

    @staticmethod
    def list_runs(experiment_name: str, limit: int = 10) -> None:
        """
        List runs in an experiment.

        Args:
            experiment_name: Name of experiment
            limit: Maximum number of runs to display
        """
        try:
            experiment = mlflow.get_experiment_by_name(experiment_name)
            if not experiment:
                print(f"❌ Experiment not found: {experiment_name}")
                return

            runs = mlflow.search_runs(
                experiment_ids=[experiment.experiment_id], max_results=limit
            )

            if runs.empty:
                print(f"ℹ️  No runs found in '{experiment_name}'")
                return

            print(f"\n🏃 Recent Runs in '{experiment_name}':")
            print("=" * 80)

            for idx, run in runs.iterrows():
                print(f"\n{idx + 1}. {run.get('tags.mlflow.runName', 'Unnamed')}")
                print(f"   ID: {run['run_id']}")
                print(f"   Status: {run['status']}")

        except Exception as e:
            print(f"❌ Error listing runs: {str(e)}")


def initialize_mlflow(tracking_uri: str = "http://localhost:5000") -> MLflowSetup:
    """
    Initialize MLflow setup.

    Args:
        tracking_uri: MLflow server URI

    Returns:
        MLflowSetup instance
    """
    print(f"🚀 Initializing MLflow ({tracking_uri})...")

    setup = MLflowSetup(tracking_uri=tracking_uri)

    # Create experiments
    print("\n📝 Creating experiments...")
    experiments = setup.create_experiments()

    # List experiments
    print("\n📋 Listing all experiments...")
    setup.list_experiments()

    print("\n✅ MLflow setup complete!")
    print(f"   Dashboard: {tracking_uri}")
    print(f"   Experiments: {len(experiments)}")

    return setup


if __name__ == "__main__":
    # Example usage
    print("MLflow Setup - Task #15\n")

    # Initialize MLflow
    mlflow_setup = initialize_mlflow()

    # List experiments
    mlflow_setup.list_experiments()

    # Example: Log a forecasting run
    print("\n" + "=" * 80)
    print("Example: Logging a Load Forecasting Run")
    print("=" * 80)

    mlflow_setup.set_experiment("load-forecasting")

    run_id = mlflow_setup.log_forecast_run(
        run_name="lstm_example_v1",
        params={
            "model_type": "LSTM",
            "epochs": 50,
            "batch_size": 32,
            "learning_rate": 0.001,
            "hidden_size": 64,
            "num_layers": 2,
        },
        metrics={
            "train_loss": 0.0456,
            "test_loss": 0.0520,
            "mape": 0.12,
            "rmse": 0.048,
            "mae": 0.038,
        },
        tags={
            "version": "1.0",
            "status": "production",
        },
    )

    # List runs
    mlflow_setup.list_runs("load-forecasting")

    print("\n✅ Example complete! Visit http://localhost:5000 to view results")
