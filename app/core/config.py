from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Telegram
    bot_token: str
    # Números de teléfono autorizados, separados por comas (ej: +521234567890,+529876543210)
    # Dejar vacío para acceso abierto (no se pedirá verificación de teléfono)
    allowed_phones: str = ""

    # UiPath
    uirobot_exe: str = r"C:\Program Files\UiPath\Studio\UiRobot.exe"
    rpa_folder: str = r"C:\RPAs"
    # Whitespace-separated args inserted between UiRobot.exe and the .nupkg path
    uirobot_args: str = "execute --file"

    # Logging
    log_level: str = "INFO"
    log_file: str = "logs/bot.txt"
    log_max_bytes: int = 5_242_880
    log_backup_count: int = 3

    # Bot behavior — raw comma-separated string for the same reason as allowed_users
    menu_keywords: str = "menu,menú,bots,robots,procesos,lista,inicio,ayuda,help"
    max_queue_size: int = 10

    # ------------------------------------------------------------------
    # Parsed properties
    # ------------------------------------------------------------------

    @property
    def allowed_phones_list(self) -> List[str]:
        """Returns normalized phone numbers (digits only) for comparison."""
        import re
        return [
            re.sub(r"\D", "", p)
            for p in self.allowed_phones.split(",")
            if p.strip()
        ]

    @property
    def menu_keywords_list(self) -> List[str]:
        return [kw.strip().lower() for kw in self.menu_keywords.split(",") if kw.strip()]


_settings: "Settings | None" = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
