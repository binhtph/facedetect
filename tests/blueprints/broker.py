import asyncio
from amqtt.broker import Broker

async def main():
    broker = Broker({
        "listeners": {"default": {"type": "tcp", "bind": "127.0.0.1:18831"}},
        "sys_interval": 0,
        "auth": {"allow-anonymous": True, "plugins": ["auth_anonymous"]},
        "topic-check": {"enabled": False},
    })
    await broker.start()
    print("broker up", flush=True)
    await asyncio.Event().wait()

asyncio.run(main())
