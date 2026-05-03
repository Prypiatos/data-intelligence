import os
import sys
from datetime import datetime
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col,
    lag,
    hour,
    dayofweek,
    dayofmonth,
    avg,
    min,
    max,
    stddev,
    count,
    to_timestamp,
    date_format,
    current_timestamp,
)
from pyspark.sql.window import Window
from dotenv import load_dotenv
import logging

# ============================================
# Setup Logging
# ============================================

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

load_dotenv()

# ============================================
# Configuration
# ============================================


class Config:
    """Configuration for feature engineering pipeline."""

    # PostgreSQL Connection
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
    POSTGRES_USER = os.getenv("POSTGRES_USER")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "energy_db")

    # Security: SSL/TLS for database connections
    POSTGRES_SSL_MODE = os.getenv(
        "POSTGRES_SSL_MODE", "require"
    )  # require, disable, allow, prefer

    @staticmethod
    def validate_postgres_config():
        """Validate PostgreSQL configuration. Raises error if required vars are missing."""
        required_vars = ["POSTGRES_USER", "POSTGRES_PASSWORD"]
        missing_vars = [var for var in required_vars if not os.getenv(var)]

        if missing_vars:
            raise ValueError(
                f"❌ Missing required environment variables: {', '.join(missing_vars)}. "
                "These are critical for database security. Set them before running."
            )

        if Config.POSTGRES_PORT < 1 or Config.POSTGRES_PORT > 65535:
            raise ValueError(f"❌ Invalid POSTGRES_PORT: {Config.POSTGRES_PORT}")

        logger.info("✅ PostgreSQL configuration validated")

    # Tables (PostgreSQL schema)
    RAW_TABLE = (
        "telemetry_readings"  # Source: raw telemetry with voltage, current, power
    )
    NODE_METADATA_TABLE = "node_metadata"  # Source: node type and location info
    HOURLY_TABLE = "hourly_energy_readings"  # Intermediate: aggregated to hourly
    FEATURES_TABLE = "energy_features"  # Output: engineered features
    FORECASTS_TABLE = "forecasts"  # Output: forecast predictions

    # Spark Configuration
    SPARK_MASTER = os.getenv("SPARK_MASTER", "local")
    SPARK_CORES = int(os.getenv("SPARK_CORES", "4"))
    SPARK_MEMORY = os.getenv("SPARK_MEMORY", "2g")

    # Data Sampling (0.5Hz means 1 reading every 2 seconds)
    SAMPLING_RATE_HZ = 0.5
    READINGS_PER_HOUR = int(3600 / (1 / SAMPLING_RATE_HZ))  # 7,200 readings per hour
    READINGS_PER_DAY = READINGS_PER_HOUR * 24  # 172,800 readings per day
    READINGS_PER_WEEK = READINGS_PER_DAY * 7  # 1,209,600 readings per week

    # Feature Windows (in terms of readings, not hours)
    LAG_READINGS = {
        "lag_1h": READINGS_PER_HOUR,
        "lag_24h": READINGS_PER_DAY,
        "lag_168h": READINGS_PER_WEEK,
    }

    # Rolling Windows (in hours)
    ROLLING_HOURS = [24, 168, 720]  # 1 day, 7 days, 30 days

    @staticmethod
    def get_jdbc_url():
        """Get PostgreSQL JDBC connection URL with SSL/TLS support."""
        jdbc_url = f"jdbc:postgresql://{Config.POSTGRES_HOST}:{Config.POSTGRES_PORT}/{Config.POSTGRES_DB}"

        # Add SSL parameters for secure connections
        ssl_params = f"?sslmode={Config.POSTGRES_SSL_MODE}&connectTimeout=30"

        return jdbc_url + ssl_params


# ============================================
# Spark Session Initialization
# ============================================


def create_spark_session() -> SparkSession:
    """Create and configure Spark session."""
    logger.info("Creating Spark session...")

    try:
        spark = (
            SparkSession.builder.appName("EnergyFeatureEngineering_0_5Hz")
            .master(Config.SPARK_MASTER)
            .config("spark.driver.memory", Config.SPARK_MEMORY)
            .config("spark.executor.cores", Config.SPARK_CORES)
            .config("spark.sql.shuffle.partitions", "200")
            .getOrCreate()
        )

        spark.sparkContext.setLogLevel("INFO")

        logger.info("✅ Spark session created successfully")
        return spark

    except Exception as e:
        logger.error(f"❌ Failed to create Spark session: {str(e)}")
        raise


# ============================================
# Data Loading
# ============================================


def read_raw_data(spark):
    """
    Read raw telemetry data from PostgreSQL.

    Returns a DataFrame with columns: node_id, timestamp, voltage, current, power, energy_wh
    """
    try:
        logger.info("=" * 80)
        logger.info("📖 STAGE 1: Read Raw Telemetry Data")
        logger.info("=" * 80)

        # Read from PostgreSQL
        df = (
            spark.read.format("jdbc")
            .option("url", Config.get_jdbc_url())
            .option("dbtable", Config.RAW_TABLE)
            .option("user", Config.POSTGRES_USER)
            .option("password", Config.POSTGRES_PASSWORD)
            .option("driver", "org.postgresql.Driver")
            .load()
        )

        row_count = df.count()
        logger.info(f"✅ Read {row_count:,} rows from {Config.RAW_TABLE}")
        logger.info("   Sampling rate: 0.5Hz (1 reading every 2 seconds)")
        logger.info(
            f"   Approximate duration: {row_count / Config.READINGS_PER_HOUR:.1f} hours"
        )

        # Show sample
        logger.info("Sample raw data (0.5Hz):")
        df.orderBy("timestamp").limit(5).show(truncate=False)

        return df

    except Exception as e:
        logger.error(f"❌ Failed to read raw data: {str(e)}")
        raise


# ============================================
# Aggregation: 0.5Hz to Hourly
# ============================================


def aggregate_to_hourly(df):
    """
    Aggregate telemetry data to hourly readings by node.

    Groups readings by node and hour, then calculates:
    - avg_power: Average power over the hour
    - avg_voltage: Average voltage over the hour
    - avg_current: Average current over the hour
    - min_power: Minimum power in the hour
    - max_power: Maximum power in the hour
    - std_power: Standard deviation in the hour
    - avg_energy_wh: Average energy consumed in the hour
    - reading_count: Number of readings in the hour

    Returns:
        DataFrame with hourly aggregated data grouped by node_id
    """
    logger.info("Aggregating telemetry data to hourly by node...")

    try:
        # Convert Unix timestamp (ms) to seconds if needed, then to datetime for hour bucketing
        df_with_dt = df.withColumn(
            "dt", to_timestamp(col("timestamp") / 1000)  # Convert ms to seconds
        )

        # Group by node and hour
        hourly_df = (
            df_with_dt.withColumn(
                "hour_bucket", date_format(col("dt"), "yyyy-MM-dd HH:00:00")
            )
            .withColumn("hour_bucket_ts", to_timestamp(col("hour_bucket")))
            .groupBy("node_id", "hour_bucket_ts")
            .agg(
                avg(col("power")).alias("avg_power"),
                avg(col("voltage")).alias("avg_voltage"),
                avg(col("current")).alias("avg_current"),
                min(col("power")).alias("min_power"),
                max(col("power")).alias("max_power"),
                stddev(col("power")).alias("std_power"),
                avg(col("energy_wh")).alias("avg_energy_wh"),
                count(col("power")).alias("reading_count"),
            )
            .withColumn("timestamp", col("hour_bucket_ts"))
            .drop("hour_bucket_ts")
            .select(
                "node_id",
                "timestamp",
                "avg_power",
                "avg_voltage",
                "avg_current",
                "min_power",
                "max_power",
                "std_power",
                "avg_energy_wh",
                "reading_count",
            )
            .orderBy("node_id", "timestamp")
        )

        hourly_count = hourly_df.count()
        logger.info(f"✅ Aggregated to {hourly_count:,} hourly readings by node")
        logger.info(f"   Original readings: {df.count():,}")
        logger.info(f"   Reduction ratio: {df.count() / hourly_count:.0f}:1")

        # Show sample by node
        logger.info("Sample hourly data (by node):")
        hourly_df.orderBy("node_id", "timestamp").limit(5).show(truncate=False)
        return hourly_df

    except Exception as e:
        logger.error(f"❌ Aggregation failed: {str(e)}")
        raise


# ============================================
# Feature Engineering (on hourly data)
# ============================================


def engineer_features(df):
    """
    Create engineered features from hourly aggregated data by node.

    Features:
    - Time features: hour, day_of_week, day_of_month
    - Lag features: lag_1h, lag_24h, lag_168h (based on hourly data, per node)
    - Rolling averages: 1-day, 7-day, 30-day (in hours, per node)
    - Rolling statistics: min, max, std (24-hour window, per node)

    Returns:
        DataFrame with engineered features grouped by node_id
    """
    logger.info("Engineering features from hourly data...")

    try:
        # ============================================
        # 1. Time-Based Features
        # ============================================

        logger.info("  Creating time-based features...")

        df_with_time = (
            df.withColumn("hour", hour(col("timestamp")))
            .withColumn("day_of_week", dayofweek(col("timestamp")))
            .withColumn("day_of_month", dayofmonth(col("timestamp")))
        )

        logger.info("  ✅ Time features created")

        # ============================================
        # 2. Lag Features (on hourly data, per node)
        # ============================================

        logger.info("  Creating lag features (per node)...")

        # Window specification: order by timestamp within each node
        window_spec = Window.partitionBy("node_id").orderBy("timestamp")
        df_with_lags = df_with_time

        # lag_1h: power from 1 hour ago (1 row back)
        df_with_lags = df_with_lags.withColumn(
            "lag_1h", lag(col("avg_power"), 1).over(window_spec)
        )
        logger.info("    Created lag_1h")

        # lag_24h: power from 24 hours ago (24 rows back)
        df_with_lags = df_with_lags.withColumn(
            "lag_24h", lag(col("avg_power"), 24).over(window_spec)
        )
        logger.info("    Created lag_24h")

        # lag_168h: power from 168 hours ago / 1 week ago (168 rows back)
        df_with_lags = df_with_lags.withColumn(
            "lag_168h", lag(col("avg_power"), 168).over(window_spec)
        )
        logger.info("    Created lag_168h")

        logger.info("  ✅ Lag features created")

        # ============================================
        # 3. Rolling Window Features
        # ============================================

        logger.info("  Creating rolling window features (per node)...")

        # 24-hour window - partitioned by node, ordered by timestamp
        window_24h = (
            Window.partitionBy("node_id")
            .orderBy("timestamp")
            .rangeBetween(-24 * 3600, 0)  # -24 hours in seconds
        )

        # 7-day window - partitioned by node, ordered by timestamp
        window_7d = (
            Window.partitionBy("node_id")
            .orderBy("timestamp")
            .rangeBetween(-7 * 24 * 3600, 0)  # -7 days in seconds
        )

        # 30-day window - partitioned by node, ordered by timestamp
        window_30d = (
            Window.partitionBy("node_id")
            .orderBy("timestamp")
            .rangeBetween(-30 * 24 * 3600, 0)  # -30 days in seconds
        )

        df_with_rolling = (
            df_with_lags.withColumn(
                "rolling_avg_1d", avg(col("avg_power")).over(window_24h)
            )
            .withColumn("rolling_avg_7d", avg(col("avg_power")).over(window_7d))
            .withColumn("rolling_avg_30d", avg(col("avg_power")).over(window_30d))
            .withColumn("rolling_min_24h", min(col("min_power")).over(window_24h))
            .withColumn("rolling_max_24h", max(col("max_power")).over(window_24h))
            .withColumn("rolling_std_24h", stddev(col("avg_power")).over(window_24h))
        )

        logger.info("  ✅ Rolling window features created")

        # ============================================
        # 4. Add Metadata
        # ============================================

        logger.info("  Adding metadata...")

        df_features = (
            df_with_rolling.withColumn("feature_timestamp", col("timestamp"))
            .withColumn("created_at", current_timestamp())
            .withColumn("pipeline_version", "2.0")
            .withColumn("aggregation_level", "hourly")
        )

        logger.info("  ✅ Metadata added")

        logger.info("✅ Feature engineering complete")

        # Show sample
        logger.info("Sample engineered features (from hourly data, by node):")
        df_features.select(
            "node_id",
            "timestamp",
            "avg_power",
            "hour",
            "day_of_week",
            "rolling_avg_1d",
            "rolling_avg_7d",
            "lag_1h",
            "lag_24h",
        ).orderBy("node_id", "timestamp").limit(5).show(truncate=False)

        return df_features

    except Exception as e:
        logger.error(f"❌ Feature engineering failed: {str(e)}")
        raise


# ============================================
# Data Quality Checks
# ============================================


def validate_features(df) -> bool:
    """Validate engineered features for quality issues."""
    logger.info("Validating features...")

    try:
        # Check critical columns
        critical_cols = ["timestamp", "avg_power", "hour", "day_of_week"]
        for col_name in critical_cols:
            null_count = df.filter(col(col_name).isNull()).count()
            if null_count > 0:
                logger.warning(f"  ⚠️  {null_count} null values in {col_name}")

        # Check for negative power
        negative_count = df.filter(col("avg_power") < 0).count()
        if negative_count > 0:
            logger.warning(f"  ⚠️  {negative_count} negative power values")

        row_count = df.count()
        logger.info(f"  ✅ Total rows: {row_count:,}")

        logger.info("✅ Validation complete")
        return True

    except Exception as e:
        logger.error(f"❌ Validation failed: {str(e)}")
        return False


# ============================================
# Data Writing
# ============================================


def write_features(df, spark: SparkSession) -> bool:
    """Write engineered features to PostgreSQL."""
    logger.info(f"Writing features to {Config.FEATURES_TABLE}...")

    try:
        df.write.format("jdbc").option("url", Config.get_jdbc_url()).option(
            "dbtable", Config.FEATURES_TABLE
        ).option("user", Config.POSTGRES_USER).option(
            "password", Config.POSTGRES_PASSWORD
        ).option(
            "driver", "org.postgresql.Driver"
        ).mode(
            "overwrite"
        ).save()

        row_count = df.count()
        logger.info(f"✅ Wrote {row_count:,} rows to {Config.FEATURES_TABLE}")  #

        return True

    except Exception as e:
        logger.error(f"❌ Failed to write features: {str(e)}")
        return False


# ============================================
# Pipeline Orchestration
# ============================================


def run_feature_engineering_pipeline():
    """Run the complete feature engineering pipeline."""
    logger.info("=" * 80)
    logger.info("Starting Feature Engineering Pipeline (0.5Hz Data)")
    logger.info("=" * 80)

    start_time = datetime.now()

    try:
        # Step 0: Validate PostgreSQL configuration
        logger.info("Validating PostgreSQL configuration...")
        Config.validate_postgres_config()

        # Step 1: Create Spark session
        spark = create_spark_session()

        # Step 2: Read raw 0.5Hz data
        df_raw = read_raw_data(spark)

        # Step 3: Aggregate 0.5Hz to hourly
        df_hourly = aggregate_to_hourly(df_raw)

        # Step 4: Engineer features
        df_features = engineer_features(df_hourly)

        # Step 5: Validate features
        if not validate_features(df_features):
            logger.warning("⚠️  Some validation checks failed, proceeding anyway")

        # Step 6: Write features
        if write_features(df_features, spark):
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            logger.info("=" * 80)
            logger.info("✅ Pipeline completed successfully!")
            logger.info(f"   Duration: {duration:.2f} seconds")
            logger.info(f"   Features table: {Config.FEATURES_TABLE}")
            logger.info("   Aggregation: 0.5Hz → Hourly → Features")
            logger.info("=" * 80)

            return True
        else:
            logger.error("❌ Failed to write features")
            return False

    except Exception as e:
        logger.error(f"❌ Pipeline failed: {str(e)}")
        return False

    finally:
        try:
            spark.stop()
            logger.info("Spark session closed")
        except Exception:
            pass


# ============================================
# Main
# ============================================

if __name__ == "__main__":
    """Run feature engineering pipeline."""
    success = run_feature_engineering_pipeline()
    sys.exit(0 if success else 1)
