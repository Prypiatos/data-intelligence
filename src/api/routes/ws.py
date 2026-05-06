import asyncio
import json
import os
import threading

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from kafka import KafkaConsumer
from kafka.errors import KafkaError

router = APIRouter(tags=["websocket"])

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
RESULTS_TOPIC = "energy.telemetry.results"


def _kafka_to_queue(queue: asyncio.Queue, loop: asyncio.AbstractEventLoop, stop: threading.Event):
    try:
        consumer = KafkaConsumer(
            RESULTS_TOPIC,
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            auto_offset_reset="latest",
            enable_auto_commit=True,
            group_id=None,
            consumer_timeout_ms=500,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        )
        while not stop.is_set():
            for message in consumer:
                if stop.is_set():
                    break
                data = message.value
                required = {"node_id", "window_start", "window_end", "avg_power", "max_power", "record_count"}
                if not required.issubset(data.keys()):
                    continue
                asyncio.run_coroutine_threadsafe(queue.put(data), loop)
        consumer.close()
    except KafkaError as e:
        asyncio.run_coroutine_threadsafe(queue.put({"error": str(e)}), loop)


@router.websocket("/ws/live")
async def live_stream(websocket: WebSocket):
    await websocket.accept()
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()
    stop = threading.Event()

    thread = threading.Thread(target=_kafka_to_queue, args=(queue, loop, stop), daemon=True)
    thread.start()

    try:
        while True:
            try:
                data = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_json(data)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        stop.set()
