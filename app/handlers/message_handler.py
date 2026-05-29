import logging
import re
import unicodedata
from typing import List, Optional

from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from app.core.config import Settings
from app.repositories.rpa_repository import RpaProcess, RpaRepository
from app.services.rpa_service import QueuedTask, RpaService
from app.services.session_service import SessionService, SessionState

logger = logging.getLogger("rpa_bot.handler")


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _normalize_text(text: str) -> str:
    """Lowercase and strip accents."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _normalize_phone(phone: str) -> str:
    """Keep digits only for comparison."""
    return re.sub(r"\D", "", phone)


def _has_menu_keyword(text: str, keywords: List[str]) -> bool:
    normalized = _normalize_text(text)
    return any(_normalize_text(kw) in normalized for kw in keywords)


def _build_menu_text(processes: List[RpaProcess]) -> str:
    if not processes:
        return "⚠️ No se encontraron procesos RPA en la carpeta configurada."

    lines = ["<b>Procesos RPA disponibles:</b>\n"]
    for p in processes:
        version_tag = f" <i>v{p.version}</i>" if p.version else ""
        line = f"  <b>{p.index}.</b> {p.name}{version_tag}"
        if p.description:
            line += f"\n       <i>{p.description}</i>"
        lines.append(line)

    lines.append(
        "\nResponde con el <b>número</b> o el <b>nombre</b> del proceso que deseas ejecutar."
    )
    return "\n".join(lines)


def _contact_keyboard() -> ReplyKeyboardMarkup:
    button = KeyboardButton("📱 Compartir número de teléfono", request_contact=True)
    return ReplyKeyboardMarkup(
        [[button]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# ------------------------------------------------------------------
# Handler class
# ------------------------------------------------------------------

class BotHandlers:
    def __init__(
        self,
        settings: Settings,
        rpa_repository: RpaRepository,
        rpa_service: RpaService,
        session_service: SessionService,
    ) -> None:
        self._settings = settings
        self._repo = rpa_repository
        self._rpa = rpa_service
        self._sessions = session_service

    def register(self, app: Application) -> None:  # type: ignore[type-arg]
        app.add_handler(CommandHandler("start", self._cmd_start))
        app.add_handler(CommandHandler("help", self._cmd_help))
        app.add_handler(CommandHandler("menu", self._cmd_menu))
        app.add_handler(MessageHandler(filters.CONTACT, self._handle_contact))
        app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_message)
        )
        logger.info("Handlers registered")

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        session = self._sessions.get_or_create(
            update.effective_chat.id, _get_display_name(update)  # type: ignore[union-attr]
        )
        if not self._is_phone_check_enabled():
            session.verified = True

        if not session.verified:
            await self._request_phone(update)
            return

        await update.message.reply_text(  # type: ignore[union-attr]
            f"Hola, <b>{session.username}</b>. Bienvenido al bot de ejecución RPA.\n\n"
            "Escribe <b>menu</b> para ver los procesos disponibles.",
            parse_mode="HTML",
        )

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        session = self._get_verified_session(update)
        if session is None:
            return

        await update.message.reply_text(  # type: ignore[union-attr]
            "<b>Cómo usar el bot:</b>\n\n"
            "1. Escribe <b>menu</b>, <b>bots</b>, <b>robots</b> o <b>procesos</b> "
            "para ver la lista de RPAs disponibles.\n"
            "2. Responde con el <b>número</b> o <b>nombre</b> del proceso a ejecutar.\n"
            "3. El bot te notificará cuando el proceso <b>inicie</b> y cuando <b>finalice</b>.\n"
            "4. Los procesos se encolan; no se ejecutan dos al mismo tiempo.\n\n"
            "<b>Comandos:</b>\n"
            "/menu — Ver procesos disponibles\n"
            "/help — Esta ayuda\n"
            "/start — Mensaje de bienvenida",
            parse_mode="HTML",
        )

    async def _cmd_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        session = self._get_verified_session(update)
        if session is None:
            return
        await self._show_menu(update)

    # ------------------------------------------------------------------
    # Contact verification
    # ------------------------------------------------------------------

    async def _handle_contact(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        contact = update.message.contact  # type: ignore[union-attr]
        chat_id = update.effective_chat.id  # type: ignore[union-attr]
        username = _get_display_name(update)

        # Reject if the user forwarded someone else's contact
        if contact.user_id and contact.user_id != update.effective_user.id:  # type: ignore[union-attr]
            await update.message.reply_text(  # type: ignore[union-attr]
                "⚠️ Por favor comparte <b>tu propio</b> número de teléfono.",
                parse_mode="HTML",
                reply_markup=_contact_keyboard(),
            )
            return

        phone = _normalize_phone(contact.phone_number)
        session = self._sessions.get_or_create(chat_id, username)

        if self._is_phone_authorized(phone):
            session.verified = True
            session.phone = phone
            logger.info("User '%s' verified with phone ***%s", username, phone[-4:])
            await update.message.reply_text(  # type: ignore[union-attr]
                "✅ Número verificado. Bienvenido.\n\n"
                "Escribe <b>menu</b> para ver los procesos disponibles.",
                parse_mode="HTML",
                reply_markup=ReplyKeyboardRemove(),
            )
        else:
            logger.warning(
                "Unauthorized phone ***%s from '%s' (chat_id=%d)",
                phone[-4:], username, chat_id,
            )
            await update.message.reply_text(  # type: ignore[union-attr]
                "⛔ Tu número no tiene acceso a este bot.",
                reply_markup=ReplyKeyboardRemove(),
            )

    # ------------------------------------------------------------------
    # Main message handler
    # ------------------------------------------------------------------

    async def _on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.message.text:
            return

        session = self._get_verified_session(update)
        if session is None:
            return

        text = update.message.text.strip()
        logger.debug("Message from '%s': %s", session.username, text)

        if _has_menu_keyword(text, self._settings.menu_keywords_list):
            await self._show_menu(update)
            return

        if session.state == SessionState.AWAITING_SELECTION:
            await self._handle_selection(update, context, text, session)
            return

        await update.message.reply_text(  # type: ignore[union-attr]
            "No entendí tu mensaje.\n"
            "Escribe <b>menu</b> para ver los procesos disponibles.",
            parse_mode="HTML",
        )

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------

    async def _show_menu(self, update: Update) -> None:
        chat_id = update.effective_chat.id  # type: ignore[union-attr]
        username = _get_display_name(update)

        processes = self._repo.load()
        session = self._sessions.get_or_create(chat_id, username)
        session.shown_processes = processes
        session.state = SessionState.AWAITING_SELECTION

        await update.message.reply_text(  # type: ignore[union-attr]
            _build_menu_text(processes), parse_mode="HTML"
        )
        logger.info("Menu sent to '%s' (%d processes)", username, len(processes))

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    async def _handle_selection(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        text: str,
        session,
    ) -> None:
        shown = session.shown_processes
        process = self._resolve_exact(text, shown)

        if process is None:
            matches = self._search_in(text, shown)

            if not matches:
                await update.message.reply_text(  # type: ignore[union-attr]
                    f"No encontré ningún proceso con <b>'{text}'</b>.\n"
                    "Escribe <b>menu</b> para ver la lista de procesos disponibles.",
                    parse_mode="HTML",
                )
                logger.info("No process matched '%s' for '%s'", text, session.username)
                return

            if len(matches) > 1:
                names = "\n".join(f"  {p.index}. {p.name}" for p in matches)
                await update.message.reply_text(  # type: ignore[union-attr]
                    f"Encontré <b>{len(matches)} procesos</b> que coinciden con "
                    f"<b>'{text}'</b>:\n\n{names}\n\n"
                    "Por favor sé más específico (escribe el número o el nombre exacto).",
                    parse_mode="HTML",
                )
                return

            process = matches[0]

        await self._enqueue_process(update, context, process)

    @staticmethod
    def _resolve_exact(text: str, processes: List[RpaProcess]) -> Optional[RpaProcess]:
        stripped = text.strip()
        if stripped.isdigit():
            idx = int(stripped)
            return next((p for p in processes if p.index == idx), None)
        name_lower = stripped.lower()
        return next((p for p in processes if p.name.lower() == name_lower), None)

    @staticmethod
    def _search_in(query: str, processes: List[RpaProcess]) -> List[RpaProcess]:
        q = query.strip().lower()
        return [
            p for p in processes
            if q in p.name.lower() or q in p.filename.lower()
        ]

    # ------------------------------------------------------------------
    # Enqueue
    # ------------------------------------------------------------------

    async def _enqueue_process(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        process: RpaProcess,
    ) -> None:
        chat_id = update.effective_chat.id  # type: ignore[union-attr]
        username = _get_display_name(update)
        bot = context.bot

        async def on_start(task: QueuedTask) -> None:
            await bot.send_message(
                chat_id=task.chat_id,
                text=f"▶️ <b>Iniciando:</b> <code>{task.process.name}</code>...",
                parse_mode="HTML",
            )

        async def on_complete(task: QueuedTask, success: bool, output: str) -> None:
            icon = "✅" if success else "❌"
            status = "completado exitosamente" if success else "finalizado con error"
            msg = f"{icon} <b>{task.process.name}</b> {status}."
            if not success and output:
                snippet = output[:400]
                msg += f"\n\n<pre>{snippet}</pre>"
            await bot.send_message(
                chat_id=task.chat_id,
                text=msg,
                parse_mode="HTML",
            )

        enqueued = await self._rpa.enqueue(
            process=process,
            chat_id=chat_id,
            username=username,
            on_start=on_start,
            on_complete=on_complete,
        )

        if enqueued:
            if not self._rpa.is_running and self._rpa.queue_size == 1:
                confirm_msg = (
                    f"✅ Proceso <b>{process.name}</b> en cola.\n"
                    "Comenzará en instantes."
                )
            else:
                position = self._rpa.queue_size + (1 if self._rpa.is_running else 0)
                confirm_msg = (
                    f"⏳ Proceso <b>{process.name}</b> agregado a la cola.\n"
                    f"Posición: <b>{position}</b>"
                )
            await update.message.reply_text(confirm_msg, parse_mode="HTML")  # type: ignore[union-attr]
            logger.info("Process '%s' enqueued for '%s'", process.name, username)
        else:
            await update.message.reply_text(  # type: ignore[union-attr]
                "⚠️ La cola está llena en este momento. Intenta nuevamente más tarde.",
                parse_mode="HTML",
            )

        self._sessions.reset(chat_id)

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def _is_phone_check_enabled(self) -> bool:
        return bool(self._settings.allowed_phones.strip())

    def _is_phone_authorized(self, normalized_phone: str) -> bool:
        if not self._is_phone_check_enabled():
            return True
        return any(
            normalized_phone.endswith(allowed) or allowed.endswith(normalized_phone)
            for allowed in self._settings.allowed_phones_list
        )

    def _get_verified_session(self, update: Update):
        """Returns the session if the user is verified, otherwise triggers phone request."""
        chat_id = update.effective_chat.id  # type: ignore[union-attr]
        username = _get_display_name(update)
        session = self._sessions.get_or_create(chat_id, username)

        if not self._is_phone_check_enabled():
            session.verified = True
            return session

        if session.verified:
            return session

        import asyncio
        asyncio.create_task(self._request_phone(update))
        return None

    async def _request_phone(self, update: Update) -> None:
        await update.message.reply_text(  # type: ignore[union-attr]
            "👋 Para usar este bot necesitas verificar tu número de teléfono.\n\n"
            "Toca el botón de abajo para compartirlo.",
            reply_markup=_contact_keyboard(),
        )
        logger.info(
            "Phone verification requested for '%s' (chat_id=%d)",
            _get_display_name(update),
            update.effective_chat.id,  # type: ignore[union-attr]
        )


# ------------------------------------------------------------------
# Utility
# ------------------------------------------------------------------

def _get_display_name(update: Update) -> str:
    user = update.effective_user  # type: ignore[union-attr]
    if user.username:
        return user.username
    full = f"{user.first_name or ''} {user.last_name or ''}".strip()
    return full or str(user.id)
