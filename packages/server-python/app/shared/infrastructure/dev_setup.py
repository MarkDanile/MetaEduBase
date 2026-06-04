import asyncio

import app.shared.infrastructure.models  # noqa: F401
from app.shared.infrastructure.database import engine, run_migrations
from app.shared.infrastructure.seed import seed_default_data


async def init_development_database() -> None:
    try:
        await run_migrations()
        await seed_default_data()
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(init_development_database())


if __name__ == "__main__":
    main()
