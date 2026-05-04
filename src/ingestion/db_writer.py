import os

import psycopg2

_conn = None


def _get_conn():
    global _conn
    if _conn is None or _conn.closed:
        _conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "postgres"),
            database=os.getenv("POSTGRES_DB", "energy_db"),
            user=os.getenv("POSTGRES_USER", "energy_user"),
            password=os.getenv("POSTGRES_PASSWORD", "energy_pass"),
        )
    return _conn


def insert_telemetry(data):
    try:
        conn = _get_conn()
        cursor = conn.cursor()
        query = """
        INSERT INTO telemetry_readings (
            node_id, timestamp, voltage, current, power, energy_wh
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (node_id, timestamp) DO NOTHING;
        """

        cursor.execute(
            query,
            (
                data["node_id"],
                data["timestamp"],
                data["voltage"],
                data["current"],
                data["power"],
                data["energy_wh"],
            ),
        )

        inserted = cursor.rowcount == 1
        conn.commit()

        if inserted:
            print("Inserted into PostgreSQL")
            return True

        print("Duplicate telemetry skipped in PostgreSQL")
        return False

    except Exception as error:
        try:
            _get_conn().rollback()
        except Exception:
            pass

        print("WARNING: PostgreSQL insert failed:", error)
        return None
