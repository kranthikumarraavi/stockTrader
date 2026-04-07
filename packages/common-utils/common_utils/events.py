"""RabbitMQ event bus for async inter-service communication.

Supports publishing and subscribing to events across services.
Falls back gracefully when RabbitMQ is unavailable.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

_log = logging.getLogger(__name__)

# Well-known event types
MARKET_DATA_UPDATED = "market_data_updated"
MODEL_TRAINED = "model_trained"
PREDICTION_GENERATED = "prediction_generated"
TRADE_SIGNAL_CREATED = "trade_signal_created"
TRADE_EXECUTED = "trade_executed"


@dataclass
class Event:
    """A domain event."""
    type: str
    data: dict[str, Any]
    source: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    correlation_id: str = ""


class EventBus:
    """RabbitMQ-backed event bus with graceful degradation.

    If RabbitMQ is unavailable, events are logged but not lost-fatal.
    """

    def __init__(self, rabbitmq_url: str | None = None, exchange: str = "stocktrader.events"):
        self._url = rabbitmq_url or os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
        self._exchange = exchange
        self._connection = None
        self._channel = None
        self._consumers: dict[str, list[Callable]] = {}
        self._connected = False

    def connect(self) -> bool:
        """Establish connection to RabbitMQ. Returns True on success."""
        try:
            import pika

            params = pika.URLParameters(self._url)
            params.connection_attempts = 3
            params.retry_delay = 2
            self._connection = pika.BlockingConnection(params)
            self._channel = self._connection.channel()
            self._channel.exchange_declare(
                exchange=self._exchange,
                exchange_type="topic",
                durable=True,
            )
            self._connected = True
            _log.info("Connected to RabbitMQ at %s", self._url)
            return True
        except Exception as exc:
            _log.warning("RabbitMQ unavailable (%s) – events will be logged only", exc)
            self._connected = False
            return False

    def publish(self, event: Event) -> bool:
        """Publish an event to the exchange.

        Returns True if published to RabbitMQ, False if only logged.
        """
        payload = json.dumps({
            "type": event.type,
            "data": event.data,
            "source": event.source,
            "timestamp": event.timestamp,
            "correlation_id": event.correlation_id,
        })

        if self._connected and self._channel:
            try:
                import pika

                self._channel.basic_publish(
                    exchange=self._exchange,
                    routing_key=event.type,
                    body=payload.encode(),
                    properties=pika.BasicProperties(
                        content_type="application/json",
                        delivery_mode=2,  # persistent
                    ),
                )
                _log.debug("Published event: %s", event.type)
                return True
            except Exception as exc:
                _log.warning("Failed to publish event %s: %s", event.type, exc)
                self._connected = False

        _log.info("Event (local): %s – %s", event.type, payload[:200])
        return False

    def subscribe(self, event_type: str, handler: Callable[[Event], None]) -> None:
        """Register a handler for an event type."""
        self._consumers.setdefault(event_type, []).append(handler)

    def start_consuming(self) -> None:
        """Start consuming events in a background thread.

        Only starts if connected and there are registered handlers.
        """
        if not self._connected or not self._consumers:
            _log.info("Event consumer not started (connected=%s, handlers=%d)",
                       self._connected, len(self._consumers))
            return

        def _consume():
            try:
                import pika

                for event_type, handlers in self._consumers.items():
                    queue_name = f"{event_type}.{os.getpid()}"
                    self._channel.queue_declare(queue=queue_name, auto_delete=True)
                    self._channel.queue_bind(
                        queue=queue_name,
                        exchange=self._exchange,
                        routing_key=event_type,
                    )

                    def _callback(ch, method, properties, body, _handlers=handlers):
                        try:
                            data = json.loads(body)
                            event = Event(**data)
                            for handler in _handlers:
                                handler(event)
                        except Exception as exc:
                            _log.error("Error handling event: %s", exc)
                        finally:
                            ch.basic_ack(delivery_tag=method.delivery_tag)

                    self._channel.basic_consume(
                        queue=queue_name,
                        on_message_callback=_callback,
                    )

                _log.info("Event consumer started for %d event types", len(self._consumers))
                self._channel.start_consuming()
            except Exception as exc:
                _log.error("Event consumer crashed: %s", exc)

        thread = threading.Thread(target=_consume, daemon=True, name="event-consumer")
        thread.start()

    def close(self) -> None:
        """Close the RabbitMQ connection."""
        if self._connection and not self._connection.is_closed:
            try:
                self._connection.close()
            except Exception:
                pass
        self._connected = False
