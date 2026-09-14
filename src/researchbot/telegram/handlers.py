from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from researchbot.db import repo
from researchbot.db.session import session_scope
from researchbot.research.cursor_agent import CursorAgentError
from researchbot.research.service import QueryRejectedError, ResearchBusyError
from researchbot.telegram.formatter import format_help, format_report, format_welcome

logger = logging.getLogger(__name__)

COMING_SOON = {
    "paper": "Paper-only search is next. For now, send a natural-language query.",
    "video": "Video-only search is next. For now, send a natural-language query.",
    "blog": "Blog-only search is next. For now, send a natural-language query.",
    "patent": "Patent search is planned. Not in the MVP.",
    "github": "GitHub search is planned. Not in the MVP.",
    "library": "Personal library is planned. Not in the MVP.",
}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(format_welcome())


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(format_help(), parse_mode=ParseMode.HTML)


async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    query = " ".join(context.args or []).strip()
    if not query:
        await update.message.reply_text(
            "Usage: /search inference engineering\nOr just send the question as a message."
        )
        return
    await _begin_research(update, context, query)


async def history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    async with session_scope() as session:
        user = await repo.get_or_create_user(session, update.effective_user.id)
        tasks = await repo.list_recent_tasks(session, user.id)
    if not tasks:
        await update.message.reply_text("No research history yet. Send a topic to start.")
        return
    lines = ["<b>Recent research</b>"]
    for task in tasks:
        day = task.created_at.strftime("%Y-%m-%d") if task.created_at else "unknown"
        lines.append(f"{day} · {task.status.value} · {_html(task.query)}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def coming_soon(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    command = update.message.text.split()[0].lstrip("/").split("@")[0]
    await update.message.reply_text(COMING_SOON.get(command, "That command is not available yet."))


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()
    if text.startswith("/"):
        return
    await _begin_research(update, context, text)


async def _begin_research(
    update: Update, context: ContextTypes.DEFAULT_TYPE, query: str
) -> None:
    if not update.message or not update.effective_user:
        return
    service = context.application.bot_data["research_service"]
    try:
        _task_id, job = await service.start_research(update.effective_user.id, query)
    except QueryRejectedError as exc:
        await update.message.reply_text(str(exc))
        return
    except ResearchBusyError as exc:
        await update.message.reply_text(str(exc))
        return

    jobs: set = context.application.bot_data.setdefault("jobs", set())
    jobs.add(job)
    job.add_done_callback(jobs.discard)

    chat_id = update.effective_chat.id
    await update.message.reply_text(
        "Research started. I will send the report here when it is ready. "
        "This usually takes a few minutes."
    )

    async def deliver() -> None:
        try:
            report = await job
        except CursorAgentError:
            logger.exception("Research job failed")
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "Research failed. The agent could not finish a verified report. "
                    "Try a more specific query in a few minutes."
                ),
            )
            return
        except Exception:
            logger.exception("Unhandled research error")
            await context.bot.send_message(
                chat_id=chat_id,
                text="Research failed because of an internal error. Try again later.",
            )
            return
        for chunk in format_report(report):
            await context.bot.send_message(
                chat_id=chat_id,
                text=chunk,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )

    deliver_task = context.application.create_task(deliver())
    jobs.add(deliver_task)
    deliver_task.add_done_callback(jobs.discard)


def _html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
