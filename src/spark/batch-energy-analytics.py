# Run with:
# spark-submit --packages org.postgresql:postgresql:42.6.0 src/spark/batch-energy-analytics.py

import logging
import os

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


def read_postgres_table(spark, jdbc_url, table_name, user, password):
    """Read a PostgreSQL table into a Spark DataFrame."""
    return (
        spark.read.format("jdbc")
        .option("url", jdbc_url)
        .option("dbtable", table_name)
        .option("user", user)
        .option("password", password)
        .option("driver", "org.postgresql.Driver")
        .load()
    )


def write_postgres_table(df, jdbc_url, table_name, user, password):
    """Overwrite analytics table contents, preserving schema and constraints."""
    (
        df.write.format("jdbc")
        .option("url", jdbc_url)
        .option("dbtable", table_name)
        .option("user", user)
        .option("password", password)
        .option("driver", "org.postgresql.Driver")
        .option(
            "truncate", "true"
        )  # TRUNCATE instead of DROP+CREATE — keeps constraints
        .mode("overwrite")
        .save()
    )


def main():
    """Main function to run the batch energy analytics."""
    postgres_host = os.getenv("POSTGRES_HOST", "postgres")
    postgres_port = os.getenv("POSTGRES_PORT", "5432")
    postgres_db = os.getenv("POSTGRES_DB", "energy_db")
    postgres_user = os.getenv("POSTGRES_USER", "energy_user")
    postgres_password = os.getenv("POSTGRES_PASSWORD", "energy_pass")

    jdbc_url = f"jdbc:postgresql://{postgres_host}:{postgres_port}/{postgres_db}"

    spark = SparkSession.builder.appName("BatchEnergyAnalytics").getOrCreate()
    logger.info("Spark started — using PostgreSQL: %s", jdbc_url)

    try:
        logger.info("Reading telemetry_readings")
        telemetry_df = read_postgres_table(
            spark, jdbc_url, "telemetry_readings", postgres_user, postgres_password
        ).select("node_id", "timestamp", "power", "energy_wh")

        logger.info("Reading node_metadata")
        metadata_df = read_postgres_table(
            spark, jdbc_url, "node_metadata", postgres_user, postgres_password
        ).select("node_id", "location")

        logger.info("Joining telemetry with node metadata")
        joined_df = telemetry_df.join(
            metadata_df, on="node_id", how="left"
        ).withColumnRenamed("location", "division")

        logger.info("Converting epoch-ms timestamps")
        analytics_base_df = (
            joined_df.withColumn(
                "event_time",
                from_unixtime(col("timestamp") / 1000).cast("timestamp"),
            )
            .withColumn("hour_start", date_trunc("hour", col("event_time")))
            .withColumn("date", to_date(col("event_time")))
        )

        hourly_df = analytics_base_df.groupBy("node_id", "division", "hour_start").agg(
            sum("energy_wh").alias("total_consumption_wh"),
            avg("power").alias("avg_power_w"),
            max("power").alias("peak_power_w"),
            count("*").alias("reading_count"),
        )

        daily_df = analytics_base_df.groupBy("node_id", "division", "date").agg(
            sum("energy_wh").alias("total_consumption_wh"),
            avg("power").alias("avg_power_w"),
            max("power").alias("peak_power_w"),
            count("*").alias("reading_count"),
        )

        logger.info(
            "Generated %s hourly rows, %s daily rows",
            hourly_df.count(),
            daily_df.count(),
        )

        logger.info("Writing hourly analytics")
        write_postgres_table(
            hourly_df,
            jdbc_url,
            "energy_analytics_hourly",
            postgres_user,
            postgres_password,
        )

        logger.info("Writing daily analytics")
        write_postgres_table(
            daily_df,
            jdbc_url,
            "energy_analytics_daily",
            postgres_user,
            postgres_password,
        )

        logger.info("Energy analytics written to PostgreSQL")

    finally:
        spark.stop()
        logger.info("Spark stopped")


if __name__ == "__main__":
    main()
