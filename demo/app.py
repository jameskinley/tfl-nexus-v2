import asyncio
import os
import sys
import threading

# Allow `python app.py` from within demo/ as well as package imports
_HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(_HERE)
sys.path.insert(0, _HERE)

from flask import Flask, jsonify, render_template, request
from chat import Chat

# Single persistent event loop running in a background thread.
# All async work is submitted here so the MCP SSE session stays alive
# across requests on the same loop.
_loop = asyncio.new_event_loop()
threading.Thread(target=_loop.run_forever, daemon=True).start()

def _run(coro):
    return asyncio.run_coroutine_threadsafe(coro, _loop).result()

app = Flask(__name__)
_chat = Chat()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/message", methods=["POST"])
def message():
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Message cannot be empty"}), 400
    try:
        content = _run(_chat.message(text))
        return jsonify({"content": content})
    except Exception as exc:
        app.logger.exception("Chat error")
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9003, debug=False)
