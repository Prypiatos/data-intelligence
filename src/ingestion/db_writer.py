import psycopg2

# Create connection
conn = psycopg2.connect(
    host="localhost",
    database="energy_db",
    user="energy_user",
    password="energy_pass"
)

cursor = conn.cursor()


def insert_telemetry(data):
    try:
        query = """
        INSERT INTO telemetry_readings (node_id, timestamp, voltage, current, power, energy_wh)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (node_id, timestamp) DO NOTHING;
        """

        cursor.execute(query, (
            data["node_id"],
            data["timestamp"],
            data["voltage"],
            data["current"],
            data["power"],
            data["energy_wh"]
        ))

        conn.commit()
        print("Inserted into PostgreSQL")

    except Exception as e:
        conn.rollback()  # 🔥 IMPORTANT FIX
        print("DB insert error:", e)