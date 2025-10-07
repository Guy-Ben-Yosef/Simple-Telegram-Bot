#!/usr/bin/env python3
"""
Telegram bot that:
- registers users (/start)
- every 12 hours asks all known users to send an integer N (10..100)
- when a user replies with N, generates NxN random integers in [0,100],
  computes the average of each row and sends a nicely formatted column matrix
- can be triggered immediately by any user with /trigger_now

Requires: python-telegram-bot >= 20 (async)
Set BOT_TOKEN env var before running.
"""

import asyncio
import logging
import os
import random
from typing import Set, Dict

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# In-memory structures (reset on restart)
known_users: Set[int] = set()  # user_ids
pending_users: Dict[int, bool] = {}  # user_id -> True if awaiting N
pending_lock = asyncio.Lock()  # protect pending_users

# Job interval: 12 hours in seconds
TWELVE_HOURS = 12 * 60 * 60


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Register user and send welcome message."""
    user = update.effective_user
    if not user:
        return

    user_id = user.id
    known_users.add(user_id)
    logger.info("User %s (%s) started the bot.", user_id, user.full_name)

    text = (
        f"Hello {user.first_name or 'there'}! 👋\n\n"
        "I'll ask every 12 hours for an integer N between 10 and 100. "
        "When you reply with N I'll generate an NxN matrix of random integers "
        "and reply with the column vector of row averages.\n\n"
        "You can also trigger the question immediately with /trigger_now."
    )
    await update.message.reply_text(text)


async def trigger_now_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Trigger the ask sequence immediately (for all known users)."""
    user = update.effective_user
    if user:
        known_users.add(user.id)

    logger.info("Manual trigger invoked by user %s", user.id if user else "<unknown>")
    await ask_all_users(context)


async def ask_all_users(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Ask all known users (in-memory) to send an integer between 10 and 100.
    This function is used both by the JobQueue and by /trigger_now.
    """
    if not known_users:
        logger.info("No known users to ask.")
        return

    # send message to each user and mark them pending
    async with pending_lock:
        for user_id in list(known_users):
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="Please enter an integer between 10 and 100 (inclusive).",
                )
                pending_users[user_id] = True
                logger.info("Asked user %s for integer N.", user_id)
            except Exception as e:
                # If sending fails (user blocked bot, etc.), remove from known_users
                logger.warning("Failed to message user %s: %s. Removing from known_users.", user_id, e)
                known_users.discard(user_id)
                pending_users.pop(user_id, None)


async def repeated_ask_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    JobQueue callback that runs every 12 hours.
    Delegates to ask_all_users.
    """
    logger.info("Running repeated ask job (12-hourly).")
    await ask_all_users(context)


def generate_matrix_and_row_averages(n: int):
    """Generate NxN random int matrix (0..100) and return row averages as float list."""
    matrix = [[random.randint(0, 100) for _ in range(n)] for _ in range(n)]
    averages = []
    for row in matrix:
        avg = sum(row) / len(row)
        averages.append(avg)
    return matrix, averages


def format_averages_column(averages) -> str:
    """
    Format averages as a column matrix. Use HTML <pre> for monospaced output.
    Example:
    [ 12.34 ]
    [ 56.78 ]
    """
    lines = []
    for val in averages:
        # Format with 2 decimal places, right-aligned for nicer column look
        lines.append(f"[ {val:6.2f} ]")
    joined = "\n".join(lines)
    return f"<pre>{joined}</pre>"


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Generic text handler:
    - registers user (adds to known_users)
    - if the user is in pending_users, tries to parse integer and process N
    - otherwise, ignores or replies with a short help hint
    """
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return

    user_id = user.id
    text = message.text.strip()
    known_users.add(user_id)  # register on any interaction

    # Check if this user is awaiting an N
    is_pending = False
    async with pending_lock:
        is_pending = pending_users.get(user_id, False)

    if not is_pending:
        # Not awaiting input; helpful hint
        await message.reply_text(
            "If you want me to generate a matrix now use /trigger_now (or wait for the scheduled prompt)."
        )
        return

    # Try to parse integer
    try:
        n = int(text)
    except ValueError:
        await message.reply_text("That's not an integer. Please send an integer between 10 and 100.")
        return

    if not (10 <= n <= 100):
        await message.reply_text("Please send an integer between 10 and 100 (inclusive).")
        return

    # Valid N; remove from pending
    async with pending_lock:
        pending_users.pop(user_id, None)

    await message.reply_text(f"Generating a {n}×{n} matrix of random integers (0..100). This may take a moment...")

    # Generate matrix and compute averages (this might be moderately heavy for large N; keep it synchronous)
    matrix, averages = generate_matrix_and_row_averages(n)

    # Format averages as column and send
    formatted = format_averages_column(averages)
    try:
        await message.reply_html(
            f"Here are the row averages (one per row) as a column matrix for N={n}:\n\n{formatted}",
            # parse_mode automatically HTML, but reply_html is a convenience wrapper
        )
    except Exception as e:
        logger.exception("Failed to send averages to user %s: %s", user_id, e)
        await message.reply_text("Sorry, I couldn't send the result (error occurred).")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Exception while handling an update: %s", context.error)


def main() -> None:
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN environment variable is required")

    application = ApplicationBuilder().token(token).build()

    # Commands
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("trigger_now", trigger_now_command))

    # Text messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # JobQueue: schedule repeated_ask_job to run every 12 hours
    # Start immediately as well (optional). We'll set first run to 12 hours after start,
    # but you can change 'first' to 0 to run immediately on startup.
    job_queue = application.job_queue
    # run_repeating(callback, interval_seconds, first=first_delay)
    job_queue.run_repeating(repeated_ask_job, interval=TWELVE_HOURS, first=TWELVE_HOURS)

    # Error handler
    application.add_error_handler(error_handler)

    # Start the bot
    logger.info("Starting bot...")
    application.run_polling(allowed_updates=None)  # None = all update types


if __name__ == "__main__":
    main()
