import asyncio
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy.engine import make_url

from agentlens.config import Settings
from agentlens.conversations import ConversationError


def loop_factory():
    # psycopg async connections require a Selector loop on Windows.
    return asyncio.SelectorEventLoop()


@asynccontextmanager
async def checkpoints(settings: Settings, thread_id: str | None = None):
    url = make_url(settings.database_url.get_secret_value()).set(drivername="postgresql")
    async with AsyncPostgresSaver.from_conn_string(
        url.render_as_string(hide_password=False)
    ) as saver:
        if thread_id:
            cursor = await saver.conn.execute(
                "SELECT pg_try_advisory_lock(hashtextextended(%s, 0)) AS acquired", (thread_id,)
            )
            if not (await cursor.fetchone())["acquired"]:
                raise ConversationError(409, "This thread already has an active invocation")
        # The dedicated connection releases its session lock even if the API process dies.
        yield saver


async def setup_checkpoints(settings: Settings):
    async with checkpoints(settings) as saver:
        await saver.setup()
    return {"checkpointer": "AsyncPostgresSaver", "setup": "complete"}
