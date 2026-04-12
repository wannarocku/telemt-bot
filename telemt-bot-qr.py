import os
import re
import math
import json
import io
import logging
import traceback
from html import escape
from datetime import datetime, timezone

import qrcode
import requests
from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
    MenuButtonCommands,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "")
TELEMT_BASE_URL = os.getenv("TELEMT_API_BASE", "http://127.0.0.1:9091/v1")
TELEMT_API_AUTH = os.getenv("TELEMT_API_AUTH", "")
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "5"))

USERNAME_RE = re.compile(r"[A-Za-z0-9_.-]{1,64}")
USERS_PER_PAGE = 10
TG_MESSAGE_LIMIT = 4000

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

ADMIN_IDS: set[int] = set()
for part in ADMIN_IDS_RAW.replace(" ", "").split(","):
    if not part:
        continue
    try:
        ADMIN_IDS.add(int(part))
    except ValueError:
        pass


def telemt_headers() -> dict:
    headers = {"Content-Type": "application/json"}
    if TELEMT_API_AUTH:
        headers["Authorization"] = TELEMT_API_AUTH
    return headers


def get_tls_link(links: dict) -> str | None:
    if not isinstance(links, dict):
        return None
    tls_links = links.get("tls", [])
    if isinstance(tls_links, list) and tls_links:
        return tls_links[0]
    return None


def build_qr_bytes(data: str) -> io.BytesIO:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    bio.seek(0)
    bio.name = "telemt-user-qr.png"
    return bio


def main_menu_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("👥 Пользователи", callback_data="users:0"),
            InlineKeyboardButton("➕ Создать", callback_data="help:new"),
        ],
        [
            InlineKeyboardButton("🗑 Удалить", callback_data="help:del"),
            InlineKeyboardButton("📊 Статистика", callback_data="stats"),
        ],
        [
            InlineKeyboardButton("🔄 Обновить меню", callback_data="main"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def only_home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🏠 Главное меню", callback_data="main")]]
    )


def help_keyboard(back_to: str = "main") -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("⬅ Назад", callback_data=back_to)],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="main")],
    ]
    return InlineKeyboardMarkup(keyboard)


def user_actions_keyboard(username: str, back_page: int = 0) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(
                "🧾 Информация",
                callback_data=f"info:{username}:{back_page}",
            ),
            InlineKeyboardButton(
                "🔎 Ссылка",
                callback_data=f"links:{username}:{back_page}",
            ),
            InlineKeyboardButton(
                "📷 QR",
                callback_data=f"qr:{username}:{back_page}",
            ),
        ],
        [
            InlineKeyboardButton(
                "⬅ Назад к списку", callback_data=f"users:{back_page}"
            ),
        ],
        [
            InlineKeyboardButton("🏠 Главное меню", callback_data="main"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_users_keyboard(items: list[dict], page: int = 0) -> InlineKeyboardMarkup:
    total = len(items)
    total_pages = max(1, math.ceil(total / USERS_PER_PAGE))
    page = max(0, min(page, total_pages - 1))

    start = page * USERS_PER_PAGE
    end = start + USERS_PER_PAGE
    page_items = items[start:end]

    keyboard: list[list[InlineKeyboardButton]] = []
    for u in page_items:
        username = (u.get("username") or "").strip()
        if not username:
            continue
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"👤 {username}", callback_data=f"select:{username}:{page}"
                )
            ]
        )

    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton("⬅ Пред.", callback_data=f"users:{page - 1}")
        )
    if page < total_pages - 1:
        nav_row.append(
            InlineKeyboardButton("След. ➡", callback_data=f"users:{page + 1}")
        )
    if nav_row:
        keyboard.append(nav_row)

    keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main")])

    return InlineKeyboardMarkup(keyboard)


async def guard(update: Update) -> bool:
    user = update.effective_user
    if not user:
        return False

    if user.id not in ADMIN_IDS:
        if update.effective_message:
            await update.effective_message.reply_text("Доступ запрещён.")
        return False

    return True


def api_get_users() -> tuple[bool, list[dict] | None, str | None]:
    try:
        r = requests.get(
            f"{TELEMT_BASE_URL}/users",
            headers=telemt_headers(),
            timeout=REQUEST_TIMEOUT,
        )
        data = r.json()
        if not r.ok or not data.get("ok"):
            return False, None, f"Ошибка API: {data}"
        items = data.get("data", [])
        if not isinstance(items, list):
            return (
                False,
                None,
                "Некорректный ответ API: data не является списком.",
            )
        return True, items, None
    except Exception as e:
        return False, None, f"Ошибка получения списка: {e}"


def api_get_user(username: str) -> tuple[bool, dict | None, str | None]:
    try:
        r = requests.get(
            f"{TELEMT_BASE_URL}/users/{username}",
            headers=telemt_headers(),
            timeout=REQUEST_TIMEOUT,
        )
        data = r.json()
        if not r.ok or not data.get("ok"):
            return False, None, f"Ошибка API: {data}"
        return True, data.get("data", {}), None
    except Exception as e:
        return False, None, f"Ошибка получения пользователя: {e}"


def extract_scalar_lines(obj: dict, prefix: str = "") -> list[str]:
    lines: list[str] = []
    for key, value in obj.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            lines.extend(extract_scalar_lines(value, prefix=f"{name}."))
        elif isinstance(value, list):
            if value and all(
                not isinstance(x, (dict, list)) for x in value
            ):
                lines.append(f"{name}: {', '.join(map(str, value[:10]))}")
            else:
                lines.append(f"{name}: [list, {len(value)}]")
        else:
            lines.append(f"{name}: {value}")
    return lines


def format_stats_message(payload: dict, http_status: int) -> str:
    data = payload.get("data") or {}
    inner = data.get("data") if isinstance(data, dict) else {}
    totals = inner.get("totals") if isinstance(inner, dict) else {}
    top_section = inner.get("top") if isinstance(inner, dict) else {}
    by_connections = (
        top_section.get("by_connections") if isinstance(top_section, dict) else []
    )
    by_throughput = (
        top_section.get("by_throughput") if isinstance(top_section, dict) else []
    )

    lines: list[str] = []

    # Заголовок
    lines.append("<b>Статистика runtime</b>")
    lines.append(f"HTTP: <b>{http_status}</b>")

    # Время генерации (если есть)
    gen_ts = inner.get("generated_at_epoch_secs")
    if isinstance(gen_ts, (int, float)):
        dt = datetime.fromtimestamp(gen_ts, tz=timezone.utc)
        lines.append(f"Сгенерировано (UTC): <code>{dt:%Y-%m-%d %H:%M:%S}</code>")

    lines.append("")

    # Totals
    if isinstance(totals, dict):
        lines.append("<b>Totals</b>")
        lines.append(
            f"Текущих соединений: "
            f"<code>{totals.get('current_connections', 0)}</code>"
        )
        lines.append(
            f"Мои соединения: "
            f"<code>{totals.get('current_connections_me', 0)}</code>"
        )
        lines.append(
            f"Прямые соединения: "
            f"<code>{totals.get('current_connections_direct', 0)}</code>"
        )
        lines.append(
            f"Активных пользователей: "
            f"<code>{totals.get('active_users', 0)}</code>"
        )
        lines.append("")

    # Top by connections
    if isinstance(by_connections, list) and by_connections:
        lines.append("<b>Top by connections</b>")
        for item in by_connections[:10]:
            if not isinstance(item, dict):
                continue
            username = escape(str(item.get("username", "")) or "-")
            conns = item.get("current_connections") or 0
            bytes_val = item.get("total_octets") or 0
            gib_val = bytes_val / 1024**3
            lines.append(
                f"• <b>{username}</b>: <code>{conns}</code> conns, "
                f"<code>{gib_val:.2f}</code> GiB"
            )
        lines.append("")

    # Top by throughput
    if isinstance(by_throughput, list) and by_throughput:
        lines.append("<b>Top by throughput</b>")
        for item in by_throughput[:10]:
            if not isinstance(item, dict):
                continue
            username = escape(str(item.get("username", "")) or "-")
            conns = item.get("current_connections") or 0
            bytes_val = item.get("total_octets") or 0
            gib_val = bytes_val / 1024**3
            lines.append(
                f"• <b>{username}</b>: <code>{conns}</code> conns, "
                f"<code>{gib_val:.2f}</code> GiB"
            )

    return "\n".join(lines)


async def safe_edit_or_send(
    query,
    text: str,
    reply_markup=None,
    parse_mode=None,
    disable_web_page_preview=None,
):
    try:
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview,
        )
    except BadRequest as e:
        if "Message is not modified" in str(e):
            return await query.message.reply_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview,
            )


async def post_init(application: Application) -> None:
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Показать главное меню"),
            BotCommand("help", "Справка по боту"),
            BotCommand("stats", "Статистика runtime"),
        ]
    )
    await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return

    text = (
        "Hi, this is teleMT BOT.\n\n"
        "Выбери действие в меню ниже.\n\n"
        "Команды тоже работают:\n"
        "/users — список пользователей\n"
        "/user <username> — информация о пользователе\n"
        "/new <username> — создать пользователя\n"
        "/link <username> — получить TLS ссылку\n"
        "/del <username> — удалить пользователя\n"
        "/stats — статистика runtime\n"
    )
    await update.message.reply_text(text, reply_markup=main_menu_keyboard())


async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return

    ok, items, err = api_get_users()
    if not ok:
        await update.message.reply_text(err, reply_markup=only_home_keyboard())
        return

    if not items:
        await update.message.reply_text(
            "Пользователи отсутствуют.", reply_markup=only_home_keyboard()
        )
        return

    await update.message.reply_text(
        "Список пользователей:",
        reply_markup=build_users_keyboard(items, page=0),
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return

    try:
        r = requests.get(
            f"{TELEMT_BASE_URL}/runtime/connections/summary",
            headers=telemt_headers(),
            timeout=REQUEST_TIMEOUT,
        )
        payload = r.json()
        text = format_stats_message(payload, r.status_code)
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=only_home_keyboard(),
        )
    except Exception as e:
        await update.message.reply_text(
            f"Ошибка получения статистики: {e}",
            reply_markup=only_home_keyboard(),
        )


async def new_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return

    if not context.args:
        await update.message.reply_text(
            "Использование: /new <username>",
            reply_markup=only_home_keyboard(),
        )
        return

    username = context.args[0].strip()
    if not USERNAME_RE.fullmatch(username):
        await update.message.reply_text(
            "Некорректное имя пользователя. "
            "Допустимы A-Za-z0-9_.-, длина 1-64 символа.",
            reply_markup=only_home_keyboard(),
        )
        return

    try:
        r = requests.post(
            f"{TELEMT_BASE_URL}/users",
            headers=telemt_headers(),
            json={"username": username},
            timeout=REQUEST_TIMEOUT,
        )
        data = r.json()
        if not r.ok or not data.get("ok"):
            await update.message.reply_text(
                f"Ошибка API: {data}",
                reply_markup=only_home_keyboard(),
            )
            return

        payload = data.get("data", {})
        user = payload.get("user", {})
        links = user.get("links", {})
        tls_links = links.get("tls", [])
        secret = payload.get("secret", "")

        parts: list[str] = [
            f"<b>{escape(user.get('username', username))}</b>",
            f"Secret:\n<code>{escape(secret)}</code>",
        ]
        if tls_links:
            parts.append(
                "TLS:\n"
                + "\n".join(
                    f"<code>{escape(x)}</code>" for x in tls_links[:5]
                )
            )

        await update.message.reply_text(
            "\n\n".join(parts),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=only_home_keyboard(),
        )

        tls_link = tls_links[0] if tls_links else None
        if tls_link:
            qr_bytes = build_qr_bytes(tls_link)
            await update.message.reply_photo(
                photo=qr_bytes,
                caption=f"<code>{escape(tls_link)}</code>",
                parse_mode=ParseMode.HTML,
                reply_markup=only_home_keyboard(),
            )

    except Exception as e:
        await update.message.reply_text(
            f"Ошибка создания пользователя: {e}",
            reply_markup=only_home_keyboard(),
        )


async def user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return

    if not context.args:
        await update.message.reply_text(
            "Использование: /user <username>",
            reply_markup=only_home_keyboard(),
        )
        return

    username = context.args[0].strip()
    ok, u, err = api_get_user(username)
    if not ok:
        await update.message.reply_text(
            err,
            reply_markup=only_home_keyboard(),
        )
        return

    links = u.get("links", {})
    msg = (
        f"<b>{escape(u.get('username', username))}</b>\n"
        f"Connections: <code>{u.get('current_connections')}</code>\n"
        f"Unique IPs: <code>{u.get('active_unique_ips')}</code>\n"
        f"Total octets: <code>{u.get('total_octets')}</code>\n\n"
        f"TLS links: <code>{len(links.get('tls', []))}</code>\n"
    )

    await update.message.reply_text(
        msg,
        parse_mode=ParseMode.HTML,
        reply_markup=only_home_keyboard(),
    )


async def link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return

    if not context.args:
        await update.message.reply_text(
            "Использование: /link <username>",
            reply_markup=only_home_keyboard(),
        )
        return

    username = context.args[0].strip()
    ok, u, err = api_get_user(username)
    if not ok:
        await update.message.reply_text(
            err,
            reply_markup=only_home_keyboard(),
        )
        return

    links = u.get("links", {})
    tls_links = links.get("tls", [])
    text = (
        "TLS:\n" + "\n".join(tls_links[:10])
        if tls_links
        else "Ссылок TLS нет."
    )

    await update.message.reply_text(
        text,
        disable_web_page_preview=True,
        reply_markup=only_home_keyboard(),
    )


async def delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return

    if not context.args:
        await update.message.reply_text(
            "Использование: /del <username>",
            reply_markup=only_home_keyboard(),
        )
        return

    username = context.args[0].strip()
    try:
        r = requests.delete(
            f"{TELEMT_BASE_URL}/users/{username}",
            headers=telemt_headers(),
            timeout=REQUEST_TIMEOUT,
        )
        data = r.json()
        if not r.ok or not data.get("ok"):
            await update.message.reply_text(
                f"Ошибка API: {data}",
                reply_markup=only_home_keyboard(),
            )
            return

        await update.message.reply_text(
            f"Пользователь {username!r} удалён.",
            reply_markup=only_home_keyboard(),
        )
    except Exception as e:
        await update.message.reply_text(
            f"Ошибка удаления пользователя: {e}",
            reply_markup=only_home_keyboard(),
        )


async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not await guard(update):
        return

    data = query.data or ""

    if data == "main":
        text = (
            "Hi, this is teleMT BOT.\n\n"
            "Выбери действие в меню ниже.\n\n"
            "Команды тоже работают:\n"
            "/users — список пользователей\n"
            "/user <username> — информация о пользователе\n"
            "/new <username> — создать пользователя\n"
            "/link <username> — получить TLS ссылку\n"
            "/del <username> — удалить пользователя\n"
            "/stats — статистика runtime\n"
        )
        await safe_edit_or_send(
            query,
            text,
            reply_markup=main_menu_keyboard(),
        )
        return

    if data.startswith("help:"):
        action = data.split(":", 1)[1]
        mapping = {
            "new": "Новый пользователь:\n/new <username>\n\nПример:\n/new lev",
            "del": "Удаление пользователя:\n/del <username>\n\nПример:\n/del lev",
        }
        text = mapping.get(action, "Справка недоступна.")
        await safe_edit_or_send(
            query,
            text,
            reply_markup=help_keyboard("main"),
        )
        return

    if data == "stats":
        try:
            r = requests.get(
                f"{TELEMT_BASE_URL}/runtime/connections/summary",
                headers=telemt_headers(),
                timeout=REQUEST_TIMEOUT,
            )
            payload = r.json()
            text = format_stats_message(payload, r.status_code)
        except Exception as e:
            text = f"Ошибка получения статистики: {e}"

        await safe_edit_or_send(
            query,
            text,
            reply_markup=only_home_keyboard(),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        return

    if data.startswith("users:"):
        try:
            page = int(data.split(":", 1)[1])
        except Exception:
            page = 0

        ok, items, err = api_get_users()
        if not ok:
            await safe_edit_or_send(
                query,
                err,
                reply_markup=only_home_keyboard(),
            )
            return

        if not items:
            await safe_edit_or_send(
                query,
                "Пользователей нет.",
                reply_markup=only_home_keyboard(),
            )
            return

        total = len(items)
        total_pages = max(1, math.ceil(total / USERS_PER_PAGE))
        page = max(0, min(page, total_pages - 1))
        text = f"Страница {page + 1} / {total_pages}"

        await safe_edit_or_send(
            query,
            text,
            reply_markup=build_users_keyboard(items, page=page),
        )
        return

    if data.startswith("select:"):
        parts = data.split(":")
        if len(parts) < 3:
            await safe_edit_or_send(
                query,
                "Некорректные данные кнопки.",
                reply_markup=only_home_keyboard(),
            )
            return

        username = parts[1]
        try:
            back_page = int(parts[2])
        except Exception:
            back_page = 0

        text = f"<b>{escape(username)}</b>"
        await safe_edit_or_send(
            query,
            text,
            reply_markup=user_actions_keyboard(username, back_page),
            parse_mode=ParseMode.HTML,
        )
        return

    if data.startswith("info:"):
        parts = data.split(":")
        if len(parts) < 3:
            await safe_edit_or_send(
                query,
                "Некорректные данные кнопки.",
                reply_markup=only_home_keyboard(),
            )
            return

        username = parts[1]
        try:
            back_page = int(parts[2])
        except Exception:
            back_page = 0

        ok, u, err = api_get_user(username)
        if not ok:
            await safe_edit_or_send(
                query,
                err,
                reply_markup=user_actions_keyboard(username, back_page),
            )
            return

        links = u.get("links", {})
        text = (
            f"<b>{escape(u.get('username', username))}</b>\n"
            f"Connections: <code>{u.get('current_connections')}</code>\n"
            f"Unique IPs: <code>{u.get('active_unique_ips')}</code>\n"
            f"Total octets: <code>{u.get('total_octets')}</code>\n\n"
            f"TLS links: <code>{len(links.get('tls', []))}</code>\n"
        )

        await safe_edit_or_send(
            query,
            text,
            reply_markup=user_actions_keyboard(username, back_page),
            parse_mode=ParseMode.HTML,
        )
        return

    if data.startswith("links:"):
        parts = data.split(":")
        if len(parts) < 3:
            await safe_edit_or_send(
                query,
                "Некорректные данные кнопки.",
                reply_markup=only_home_keyboard(),
            )
            return

        username = parts[1]
        try:
            back_page = int(parts[2])
        except Exception:
            back_page = 0

        ok, u, err = api_get_user(username)
        if not ok:
            await safe_edit_or_send(
                query,
                err,
                reply_markup=user_actions_keyboard(username, back_page),
            )
            return

        links = u.get("links", {})
        tls_links = links.get("tls", [])
        text = (
            "TLS:\n" + "\n".join(tls_links[:10])
            if tls_links
            else "Ссылок TLS нет."
        )

        await safe_edit_or_send(
            query,
            text,
            reply_markup=user_actions_keyboard(username, back_page),
            disable_web_page_preview=True,
        )
        return

    if data.startswith("qr:"):
        parts = data.split(":")
        if len(parts) < 3:
            await safe_edit_or_send(
                query,
                "Некорректные данные кнопки.",
                reply_markup=only_home_keyboard(),
            )
            return

        username = parts[1]
        try:
            back_page = int(parts[2])
        except Exception:
            back_page = 0

        ok, u, err = api_get_user(username)
        if not ok:
            await safe_edit_or_send(
                query,
                err,
                reply_markup=user_actions_keyboard(username, back_page),
            )
            return

        links = u.get("links", {})
        tls_link = get_tls_link(links)
        if not tls_link:
            await query.message.reply_text(
                "У пользователя нет TLS-ссылки.",
                reply_markup=user_actions_keyboard(username, back_page),
            )
            return

        qr_bytes = build_qr_bytes(tls_link)
        await query.message.reply_photo(
            photo=qr_bytes,
            caption=f"<code>{escape(tls_link)}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=user_actions_keyboard(username, back_page),
        )
        return

    await safe_edit_or_send(
        query,
        "Неизвестная команда меню.",
        reply_markup=only_home_keyboard(),
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error

    if isinstance(err, BadRequest) and "Message is not modified" in str(err):
        logger.warning("Игнорирую harmless ошибку: %s", err)
        return

    logger.error("Exception while handling an update:", exc_info=err)
    tb = "".join(traceback.format_exception(None, err, err.__traceback__))
    logger.error(tb)

    try:
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(
                "Произошла ошибка при обработке запроса.",
                reply_markup=only_home_keyboard(),
            )
    except Exception:
        pass


def main():
    if not BOT_TOKEN:
        raise RuntimeError("Не задан BOT_TOKEN")
    if not ADMIN_IDS:
        raise RuntimeError("Не задан ADMIN_IDS, например: 123456789")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("users", users))
    app.add_handler(CommandHandler("new", new_user))
    app.add_handler(CommandHandler("user", user_info))
    app.add_handler(CommandHandler("link", link))
    app.add_handler(CommandHandler("del", delete_user))
    app.add_handler(CallbackQueryHandler(handle_button))

    app.add_error_handler(error_handler)

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
