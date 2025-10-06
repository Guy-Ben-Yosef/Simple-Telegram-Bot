import os
from flask import Flask, request
import requests

app = Flask(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise RuntimeError("Set TELEGRAM_TOKEN env var")

TG_API = f"https://api.telegram.org/bot{TOKEN}"

@app.route("/", methods=["GET"])
def index():
    return "Telegram bot service - OK", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json(force=True)
    # Very small handler: if message with text, echo it
    chat_id = None
    text = ""
    if "message" in update:
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")
    # add other update types if you need
    if chat_id:
        # send a simple reply (non-blocking-ish)
        requests.post(f"{TG_API}/sendMessage", json={
            "chat_id": chat_id,
            "text": f"ECHO: {text}"
        }, timeout=5)
    return "", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
