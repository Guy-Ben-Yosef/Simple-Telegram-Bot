#!/usr/bin/env python3
# main.py (MODIFIED FOR CLOUD RUN & CLOUD SCHEDULER)

import asyncio
import logging
import os
import random
from typing import Set, Dict

from flask import Flask, request, jsonify

from telegram import Update, Bot
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    Application
)

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- In-memory structures (reset on restart) ---
known_users: Set[int] = set()
pending_users: Dict[int, bool] = {}
pending_lock = asyncio.Lock()

# --- Environment Variables ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is required")
# A secret header to verify requests from Cloud Scheduler
SCHEDULER_SECRET = os.environ.get("SCHEDULER_SECRET", "default-secret-change-me")


# --- Bot Logic (mostly unchanged) ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
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
    user = update.effective_user
    if user:
        known_users.add(user.id)
    logger.info("Manual trigger invoked by user %s", user.id if user else "<unknown>")
    await ask_all_users(context)

async def ask_all_users(context: ContextTypes.DEFAULT_TYPE) -> None:
    if not known_users:
        logger.info("No known users to ask.")
        return
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
                logger.warning("Failed to message user %s: %s. Removing from known_users.", user_id, e)
                known_users.discard(user_id)
                pending_users.pop(user_id, None)

def generate_matrix_and_row_averages(n: int):
    matrix = [[random.randint(0, 100) for _ in range(n)] for _ in range(n)]
    averages = [sum(row) / len(row) for row in matrix]
    return matrix, averages

def format_averages_column(averages) -> str:
    lines = [f"[ {val:6.2f} ]" for val in averages]
    joined = "\n".join(lines)
    return f"<pre>{joined}</pre>"

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return
    user_id = user.id
    text = message.text.strip()
    known_users.add(user_id)
    is_pending = False
    async with pending_lock:
        is_pending = pending_users.get(user_id, False)
    if not is_pending:
        await message.reply_text("If you want me to generate a matrix now use /trigger_now.")
        return
    try:
        n = int(text)
    except ValueError:
        await message.reply_text("That's not an integer. Please send an integer between 10 and 100.")
        return
    if not (10 <= n <= 100):
        await message.reply_text("Please send an integer between 10 and 100 (inclusive).")
        return
    async with pending_lock:
        pending_users.pop(user_id, None)
    await message.reply_text(f"Generating a {n}×{n} matrix...")
    _, averages = generate_matrix_and_row_averages(n)
    formatted = format_averages_column(averages)
    try:
        await message.reply_html(f"Here are the row averages for N={n}:\n\n{formatted}")
    except Exception as e:
        logger.exception("Failed to send averages to user %s: %s", user_id, e)
        await message.reply_text("Sorry, an error occurred.")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Exception while handling an update: %s", context.error)

# --- Flask Web Server Setup ---
app = Flask(__name__)
# Build the bot application once
ptb_app = ApplicationBuilder().token(BOT_TOKEN).build()
ptb_app.add_handler(CommandHandler("start", start_command))
ptb_app.add_handler(CommandHandler("trigger_now", trigger_now_command))
ptb_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
ptb_app.add_error_handler(error_handler)

@app.route("/webhook", methods=["POST"])
async def webhook():
    """Endpoint for Telegram to send updates to."""
    update_data = request.get_json()
    update = Update.de_json(update_data, ptb_app.bot)
    await ptb_app.process_update(update)
    return jsonify(success=True)

@app.route("/trigger_ask", methods=["POST"])
async def trigger_ask_handler():
    """
    Endpoint for Cloud Scheduler to call.
    Verifies the request came from Cloud Scheduler and runs the ask job.
    """
    # Security: Check for a secret header
    if request.headers.get("X-Scheduler-Secret") != SCHEDULER_SECRET:
        logger.warning("Unauthorized access attempt to /trigger_ask")
        return "Unauthorized", 401

    logger.info("Scheduler trigger received. Running ask job.")
    await ask_all_users(ptb_app)
    return jsonify(success=True)


if __name__ == "__main__":
    # This part is for local testing. gunicorn will run the 'app' object directly in production.
    # To run locally:
    # 1. Set BOT_TOKEN and SCHEDULER_SECRET environment variables.
    # 2. Run 'python main.py'
    # You will need to set up a webhook with a tool like ngrok to test Telegram messages.
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))