import logging

from telegram.ext import Application

from app.core.config import get_settings
from app.core.logger import setup_logger
from app.handlers.message_handler import BotHandlers
from app.repositories.rpa_repository import RpaRepository
from app.services.rpa_service import RpaService
from app.services.session_service import SessionService


def main() -> None:
    settings = get_settings()
    logger = setup_logger(settings)

    logger.info("=" * 60)
    logger.info("Starting RPA Bot")
    logger.info("RPA folder   : %s", settings.rpa_folder)
    logger.info("UiRobot path : %s", settings.uirobot_exe)
    logger.info("Max queue    : %d", settings.max_queue_size)
    logger.info("Log level    : %s", settings.log_level)
    logger.info("=" * 60)

    # Repositories
    rpa_repository = RpaRepository(settings.rpa_folder)

    # Services
    rpa_service = RpaService(
        uirobot_exe=settings.uirobot_exe,
        uirobot_args=settings.uirobot_args,
        max_queue_size=settings.max_queue_size,
    )
    session_service = SessionService()

    # Telegram Application
    async def on_startup(application: Application) -> None:
        rpa_service.start()
        logger.info("Bot is up and polling for messages")

    app = (
        Application.builder()
        .token(settings.bot_token)
        .post_init(on_startup)
        .build()
    )

    # Register handlers
    handlers = BotHandlers(
        settings=settings,
        rpa_repository=rpa_repository,
        rpa_service=rpa_service,
        session_service=session_service,
    )
    handlers.register(app)

    logger.info("Press Ctrl+C to stop")
    app.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()