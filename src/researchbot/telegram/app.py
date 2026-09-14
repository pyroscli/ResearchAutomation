from telegram.ext import Application, CommandHandler, MessageHandler, filters

from researchbot.config import Settings
from researchbot.research.cursor_agent import CursorResearchRuntime
from researchbot.research.service import ResearchService
from researchbot.telegram import handlers


def build_application(
    settings: Settings, runtime: CursorResearchRuntime
) -> Application:
    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .concurrent_updates(True)
        .build()
    )
    application.bot_data["settings"] = settings
    application.bot_data["research_service"] = ResearchService(settings, runtime)

    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(CommandHandler("help", handlers.help_cmd))
    application.add_handler(CommandHandler("search", handlers.search_cmd))
    application.add_handler(CommandHandler("history", handlers.history_cmd))
    for name in ("paper", "video", "blog", "patent", "github", "library"):
        application.add_handler(CommandHandler(name, handlers.coming_soon))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.on_text)
    )
    return application
