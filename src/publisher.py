"""Publish simulated vehicle telemetry and diagnostics to RabbitMQ."""

from __future__ import annotations

import argparse
import json
import sys
import time

import pika

from simulator import VehicleSimulator, create_fleet

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


def publish_json(
    channel,
    routing_key: str,
    payload: dict,
    persistent: bool = False,
) -> None:
    """Publish one JSON message to the topic exchange."""
    body = json.dumps(payload).encode("utf-8")
    properties = pika.BasicProperties(
        content_type="application/json",
        delivery_mode=2 if persistent else 1,
    )
    channel.basic_publish(
        exchange=EXCHANGE,
        routing_key=routing_key,
        body=body,
        properties=properties,
    )


def run_fleet(
    channel,
    fleet: list[VehicleSimulator],
    interval: float,
) -> None:
    """Tick every vehicle and publish telemetry (+ diagnostics when changed)."""
    print(f"Publishing {len(fleet)} vehicles every {interval}s to exchange '{EXCHANGE}'")
    print("Press Ctrl+C to stop.\n")

    while True:
        for vehicle in fleet:
            state = vehicle.tick(dt_seconds=interval)
            short_id = vehicle.vehicle_id.replace("vehicle-", "")

            telemetry_key = f"fleet.vehicle.{short_id}.telemetry"
            publish_json(
                channel,
                routing_key=telemetry_key,
                payload=vehicle.to_telemetry_dict(state),
                persistent=False,
            )
            print(
                f"[telemetry] {telemetry_key}  "
                f"speed={state.speed_kmh}  soc={state.battery_soc}"
            )

            if vehicle.diagnostic_changed():
                diag_key = f"fleet.vehicle.{short_id}.diagnostics"
                publish_json(
                    channel,
                    routing_key=diag_key,
                    payload=vehicle.to_diagnostics_dict(state),
                    persistent=True,
                )
                print(f"[diagnostics] {diag_key}  code={state.diagnostic_code}")

        time.sleep(interval)


def parse_args():
    parser = argparse.ArgumentParser(description="Fleet telemetry RabbitMQ publisher")
    parser.add_argument("--vehicles", type=int, default=5)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=5672)
    parser.add_argument("--user", default="fleet")
    parser.add_argument("--password", default="fleetpass")
    parser.add_argument("--interval", type=float, default=2.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    fleet = create_fleet(args.vehicles)

    try:
        connection, channel = connect(args.host, args.port, args.user, args.password)
    except pika.exceptions.AMQPConnectionError as exc:
        print(f"Could not connect to RabbitMQ at {args.host}:{args.port}: {exc}")
        print("Is Docker running? Try: docker compose up -d")
        return 1

    try:
        run_fleet(channel, fleet, args.interval)
    except KeyboardInterrupt:
        print("\nStopping publisher...")
    finally:
        connection.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
