"""Subscribe to fleet telemetry and diagnostics from RabbitMQ."""

from __future__ import annotations

import argparse
import json
import sys

import pika

EXCHANGE = "fleet.telemetry"


def connect(host: str, port: int, user: str, password: str):
    """Open a connection and channel; declare the topic exchange."""
    credentials = pika.PlainCredentials(user, password)
    params = pika.ConnectionParameters(
        host=host,
        port=port,
        credentials=credentials,
        heartbeat=30,
    )
    connection = pika.BlockingConnection(params)
    channel = connection.channel()

    channel.exchange_declare(
        exchange=EXCHANGE,
        exchange_type="topic",
        durable=True,
    )
    return connection, channel


def on_message(channel, method, properties, body: bytes) -> None:
    """Decode and print one JSON message."""
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"[error] bad message on {method.routing_key}: {exc}")
        channel.basic_ack(delivery_tag=method.delivery_tag)
        return

    kind = method.routing_key.rsplit(".", 1)[-1]

    record = {
        "routing_key": method.routing_key,
        "message_type": kind,
        "payload": payload,
    }

    with open("records.jsonl", "a", encoding="utf-8") as file:
        file.write(json.dumps(record) + "\n")

    channel.basic_ack(delivery_tag=method.delivery_tag)


def run_subscriber(channel, patterns: list[str], queue_name: str) -> None:
    """Bind queue to routing-key patterns and start consuming."""
    result = channel.queue_declare(queue=queue_name, exclusive=not queue_name)
    queue = result.method.queue

    for pattern in patterns:
        channel.queue_bind(exchange=EXCHANGE, queue=queue, routing_key=pattern)
        print(f"Bound queue '{queue}' to '{pattern}'")

    channel.basic_qos(prefetch_count=10)
    channel.basic_consume(queue=queue, on_message_callback=on_message)

    print(f"Listening on exchange '{EXCHANGE}'. Press Ctrl+C to stop.\n")
    channel.start_consuming()


def parse_args():
    parser = argparse.ArgumentParser(description="Fleet telemetry RabbitMQ subscriber")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=5672)
    parser.add_argument("--user", default="fleet")
    parser.add_argument("--password", default="fleetpass")
    parser.add_argument(
        "--pattern",
        action="append",
        dest="patterns",
        help="Routing-key pattern (repeatable). Default: all fleet traffic.",
    )
    parser.add_argument(
        "--queue",
        default="",
        help="Named durable queue (empty = exclusive auto-delete queue).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    patterns = args.patterns or [
        "fleet.vehicle.*.telemetry",
        "fleet.vehicle.*.diagnostics",
    ]

    try:
        connection, channel = connect(args.host, args.port, args.user, args.password)
    except pika.exceptions.AMQPConnectionError as exc:
        print(f"Could not connect to RabbitMQ at {args.host}:{args.port}: {exc}")
        print("Is Docker running? Try: docker compose up -d")
        return 1

    try:
        run_subscriber(channel, patterns, args.queue)
    except KeyboardInterrupt:
        print("\nStopping subscriber...")
        channel.stop_consuming()
    finally:
        connection.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
