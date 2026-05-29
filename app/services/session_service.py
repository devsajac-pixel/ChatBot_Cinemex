import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional

from app.repositories.rpa_repository import RpaProcess

logger = logging.getLogger("rpa_bot.session")


class SessionState(Enum):
    IDLE = auto()
    AWAITING_SELECTION = auto()


@dataclass
class UserSession:
    chat_id: int
    username: str
    state: SessionState = SessionState.IDLE
    shown_processes: List[RpaProcess] = field(default_factory=list)
    verified: bool = False
    phone: str = ""


class SessionService:
    def __init__(self) -> None:
        self._sessions: Dict[int, UserSession] = {}

    def get_or_create(self, chat_id: int, username: str) -> UserSession:
        if chat_id not in self._sessions:
            self._sessions[chat_id] = UserSession(chat_id=chat_id, username=username)
            logger.debug("Session created for '%s' (chat_id=%d)", username, chat_id)
        return self._sessions[chat_id]

    def get(self, chat_id: int) -> Optional[UserSession]:
        return self._sessions.get(chat_id)

    def reset(self, chat_id: int) -> None:
        session = self._sessions.get(chat_id)
        if session:
            session.state = SessionState.IDLE
            session.shown_processes = []
            logger.debug("Session reset for chat_id=%d", chat_id)
