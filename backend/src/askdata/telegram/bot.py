"""Interactive Telegram bot: users send questions → get SQL results + chart PNG."""
import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, BufferedInputFile

logger = logging.getLogger(__name__)

dp = Dispatcher()

_WELCOME = (
    "👋 <b>AskData Bot</b>\n\n"
    "Задайте вопрос на русском языке — я выполню SQL-запрос к базе данных "
    "Drivee и верну результат в виде графика или таблицы.\n\n"
    "<i>Примеры:</i>\n"
    "• Топ 5 водителей по выручке за апрель\n"
    "• Сколько поездок было за последнюю неделю\n"
    "• Распределение заказов по городам"
)


@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(_WELCOME, parse_mode="HTML")


@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(_WELCOME, parse_mode="HTML")


@dp.message(F.text)
async def handle_question(message: Message):
    question = (message.text or "").strip()
    if not question:
        return

    thinking = await message.answer("⏳ Выполняю запрос…")

    try:
        result = await _run_pipeline(question)
    except Exception as e:
        logger.error("Bot pipeline error: %s", e, exc_info=True)
        await thinking.delete()
        await message.answer(f"❌ Ошибка: {e}", parse_mode="HTML")
        return

    await thinking.delete()

    if result.get("error"):
        await message.answer(f"❌ {result['error']}", parse_mode="HTML")
        return

    rows = result.get("rows", [])
    sql = result.get("sql", "")
    confidence = result.get("confidence", 0.0)
    report_name = question[:80]

    caption = _build_caption(question, rows, confidence, sql)

    from askdata.schedules.scheduler import _render_chart_png
    chart_bytes = _render_chart_png(report_name, rows, result.get("chart_config"))

    if chart_bytes:
        photo = BufferedInputFile(chart_bytes, filename="result.png")
        await message.answer_photo(photo=photo, caption=caption, parse_mode="HTML")
    else:
        text = caption + _build_text_table(rows)
        await message.answer(text, parse_mode="HTML")


def _build_caption(question: str, rows: list, confidence: float, sql: str) -> str:
    conf_pct = int(confidence * 100)
    if conf_pct >= 80:
        conf_emoji = "🟢"
    elif conf_pct >= 50:
        conf_emoji = "🟡"
    else:
        conf_emoji = "🔴"

    lines = [
        f"<b>{question[:100]}</b>",
        f"Строк: {len(rows)} {conf_emoji} {conf_pct}%",
    ]
    return "\n".join(lines) + "\n\n"


def _build_text_table(rows: list) -> str:
    if not rows:
        return "<i>Нет данных</i>"
    cols = list(rows[0].keys())
    header = " | ".join(str(c) for c in cols[:5])
    lines = [f"<pre>{header}"]
    for row in rows[:8]:
        lines.append(" | ".join(str(row.get(c, "")) for c in cols[:5]))
    if len(rows) > 8:
        lines.append(f"… ещё {len(rows) - 8} строк")
    lines.append("</pre>")
    return "\n".join(lines)


async def _run_pipeline(question: str) -> dict:
    from askdata.query.pipeline import run_pipeline
    result = await run_pipeline(question, history=[], session_id=None)
    return result


async def run_bot():
    from askdata.config import get_settings
    settings = get_settings()
    token = settings.telegram_bot_token
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN not set — bot will not start")
        return

    bot = Bot(token=token)
    logger.info("Telegram bot starting (polling)…")
    try:
        await dp.start_polling(bot, allowed_updates=["message"])
    finally:
        await bot.session.close()
