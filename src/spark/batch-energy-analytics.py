# Run with:
# spark-submit --packages org.postgresql:postgresql:42.6.0 data-intelligence/src/spark/batch-energy-analytics.py

import os
import logging

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    avg,
    col,
    count,
    date_trunc,
    from_unixtime,
    max,
    sum,
    to_date,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_env(name, default=None):
    """Helper to read environment variables with an optional default value."""
    return os.getenv(name, default)


def read_postgres_table(spark, jdbc_url, table_name, postgres_user, postgres_password):
    """Read a PostgreSQL table into a Spark DataFrame."""
    return (
        spark.read.format("jdbc")
        .option("url", jdbc_url)
        .option("dbtable", table_name)
        .option("user", postgres_user)
        .option("password", postgres_password)
        .option("driver", "org.postgresql.Driver")
        .load()
    )


def write_postgres_table(df, jdbc_url, table_name, postgres_user, postgres_password):
    """Write a Spark DataFrame to a PostgreSQL table."""
    (
        df.write.format("jdbc")
        .option("url", jdbc_url)
        .option("dbtable", table_name)
        .option("user", postgres_user)
        .option("password", postgres_password)
        .option("driver", "org.postgresql.Driver")
        .mode("append")
        .save()
    )


def main():
    """Main function to run the batch energy analytics."""
    postgres_host = get_env("POSTGRES_HOST", "postgres")
    postgres_port = get_env("POSTGRES_PORT", "5432")
    postgres_db = get_env("POSTGRES_DB", "energy_db")
    postgres_user = get_env("POSTGRES_USER", "energy_user")
    postgres_password = get_env("POSTGRES_PASSWORD", "energy_pass")

    jdbc_url = f"jdbc:postgresql://{postgres_host}:{postgres_port}/{postgres_db}"

    spark = SparkSession.builder.appName("BatchEnergyAnalytics").getOrCreate()

    logger.info("Spark started")
    logger.info("Using PostgreSQL database: %s", jdbc_url)

    logger.info("Reading telemetry_readings table")
    telemetry_df = read_postgres_table(
        spark,
        jdbc_url,
        "telemetry_readings",
        postgres_user,
        postgres_password,
    ).select("node_id", "timestamp", "power", "energy_wh")

    logger.info("Reading node_metadata table")
    metadata_df = read_postgres_table(
        spark,
        jdbc_url,
        "node_metadata",
        postgres_user,
        postgres_password,
    ).select("node_id", "location")

    logger.info("Joining telemetry readings with node metadata")
    joined_df = telemetry_df.join(
        metadata_df, on="node_id", how="left"
    ).withColumnRenamed("location", "division")

    logger.info("Converting epoch-millisecond timestamps")
    analytics_base_df = (
        joined_df.withColumn(
            "event_time",
            from_unixtime(col("timestamp") / 1000).cast("timestamp"),
        )
        .withColumn("hour_start", date_trunc("hour", col("event_time")))
        .withColumn("date", to_date(col("event_time")))
    )

    logger.info("Creating hourly energy analytics")
    hourly_df = analytics_base_df.groupBy("node_id", "division", "hour_start").agg(
        sum("energy_wh").alias("total_consumption_wh"),
        avg("power").alias("avg_power_w"),
        max("power").alias("peak_power_w"),
        count("*").alias("reading_count"),
    )

    logger.info("Creating daily energy analytics")
    daily_df = analytics_base_df.groupBy("node_id", "division", "date").agg(
        sum("energy_wh").alias("total_consumption_wh"),
        avg("power").alias("avg_power_w"),
        max("power").alias("peak_power_w"),
        count("*").alias("reading_count"),
    )

    hourly_count = hourly_df.count()
    daily_count = daily_df.count()
    logger.info("Generated %s hourly analytics rows", hourly_count)
    logger.info("Generated %s daily analytics rows", daily_count)

    logger.info("Writing hourly analytics to PostgreSQL")
    write_postgres_table(
        hourly_df,
        jdbc_url,
        "energy_analytics_hourly",
        postgres_user,
        postgres_password,
    )

    logger.info("Writing daily analytics to PostgreSQL")
    write_postgres_table(
        daily_df,
        jdbc_url,
        "energy_analytics_daily",
        postgres_user,
        postgres_password,
    )

    logger.info("Energy analytics written to PostgreSQL")

    spark.stop()
    logger.info("Spark stopped")


if __name__ == "__main__":
    main()
