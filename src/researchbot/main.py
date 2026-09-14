from __future__ import annotations

import asyncio
import logging

from researchbot.config import get_settings
from researchbot.db.session import dispose_engine, init_db
from researchbot.research.cursor_agent import CursorResearchRuntime
from researchbot.telegram.app import build_application


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.INFO)


async def async_main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    await init_db(settings)

    runtime = CursorResearchRuntime(settings)
    await runtime.start()
    application = build_application(settings, runtime)

    try:
        await application.initialize()
        await application.start()
        if application.updater is None:
            raise RuntimeError("Telegram updater is not available")
        await application.updater.start_polling(drop_pending_updates=True)
        await asyncio.Event().wait()
    finally:
        if application.updater is not None:
            await application.updater.stop()
        await application.stop()
        await application.shutdown()
        await runtime.close()
        await dispose_engine()


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
