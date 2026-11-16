"""Flask webhook server for the LinkBot GitHub App.

Endpoints:
  POST /webhook   – receives GitHub webhook events
  GET  /health    – health check (no secrets)

All webhook payloads are verified with HMAC-SHA256 before processing.
"""

import json
import logging
import threading

from flask import Flask, request, jsonify

from . import webhook_verify, scanner
from .auth import clear_cache

logger = logging.getLogger("linkbot.app")

app = Flask("linkbot")
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/webhook", methods=["POST"])
def webhook():
    # --- Verify HMAC signature ---
    payload = request.get_data()
    signature = request.headers.get("X-Hub-Signature-256")
    if not webhook_verify.verify(payload, signature):
        logger.warning("Webhook signature verification failed")
        return jsonify({"error": "invalid signature"}), 401

    event = request.headers.get("X-GitHub-Event", "")
    try:
        body = json.loads(payload)
    except (json.JSONDecodeError, ValueError):
        return jsonify({"error": "invalid JSON"}), 400

    action = body.get("action", "")
    logger.info("Received event=%s action=%s", event, action)

    # --- Handle installation events ---
    if event == "installation":
        if action == "deleted":
            installation_id = body.get("installation", {}).get("id")
            if installation_id:
                clear_cache(installation_id)
                logger.info("Installation %s removed – cache cleared",
                            installation_id)
            return jsonify({"status": "ok"}), 200

        if action == "created":
            installation_id = body.get("installation", {}).get("id")
            if installation_id:
                # Trigger initial scan in background thread
                threading.Thread(
                    target=_safe_scan,
                    args=(installation_id,),
                    daemon=True,
                ).start()
            return jsonify({"status": "accepted"}), 202

    # --- Handle installation_repositories events ---
    if event == "installation_repositories":
        installation_id = body.get("installation", {}).get("id")
        if installation_id and action in ("added",):
            threading.Thread(
                target=_safe_scan,
                args=(installation_id,),
                daemon=True,
            ).start()
            return jsonify({"status": "accepted"}), 202

    # --- Handle scheduled / manual triggers ---
    # (In production, a separate scheduler calls scan_installation periodically.
    #  A custom "scan" event could also be used via workflow_dispatch.)
    if event == "schedule" or (event == "repository" and action == "linkbot_scan"):
        installation_id = body.get("installation", {}).get("id")
        if installation_id:
            threading.Thread(
                target=_safe_scan,
                args=(installation_id,),
                daemon=True,
            ).start()
            return jsonify({"status": "accepted"}), 202

    return jsonify({"status": "ignored"}), 200


def _safe_scan(installation_id: int) -> None:
    """Run a scan, catching all exceptions to avoid crashing the thread."""
    try:
        results = scanner.scan_installation(installation_id)
        logger.info("Scan complete for installation %s: %d repos",
                     installation_id, len(results))
    except Exception:
        logger.exception("Scan failed for installation %s", installation_id)


def create_app():
    """Application factory for production use (e.g. gunicorn)."""
    return app
