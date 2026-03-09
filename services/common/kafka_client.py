import json
from typing import Any

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from .config import settings


class KafkaProducerClient:
    def __init__(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )

    async def start(self) -> None:
        await self._producer.start()

    async def stop(self) -> None:
        await self._producer.stop()

    async def send(self, topic: str, message: dict[str, Any]) -> None:
        await self._producer.send_and_wait(topic, message)


class KafkaConsumerClient:
    def __init__(self, topic: str, group_id: str):
        self._consumer = AIOKafkaConsumer(
            topic,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=group_id,
            enable_auto_commit=True,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        )

    async def start(self) -> None:
        await self._consumer.start()

    async def stop(self) -> None:
        await self._consumer.stop()

    async def messages(self):
        async for msg in self._consumer:
            yield msg.value
