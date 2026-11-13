"""Flask web API + single-page UI for AetherOS."""
import hmac
import logging
import threading
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

import config
from tools import hardware

log = logging.getLogger("aetheros.api")
STATIC = Path(__file__).parent / "static"


def create_app(system, token=None):
    app = Flask(__name__, static_folder=None)
    # The kernel keeps per-run state, so serialize AI calls.
    ai_lock = threading.Lock()

    @app.before_request
    def check_token():
        if not token or not request.path.startswith("/api/"):
            return None
        supplied = request.headers.get("X-API-Token", "")
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            supplied = auth[7:]
        if not hmac.compare_digest(supplied, token):
            return jsonify(error="Unauthorized"), 401
        return None

    @app.errorhandler(Exception)
    def on_error(e):
        code = getattr(e, "code", 500)
        if code == 500 or not isinstance(code, int):
            log.exception("Unhandled API error")
            return jsonify(error="Internal error: " + str(e)), 500
        return jsonify(error=getattr(e, "description", str(e))), code

    def body_field(name):
        data = request.get_json(silent=True) or {}
        value = data.get(name)
        if not isinstance(value, str) or not value.strip():
            return None, (jsonify(error=f"'{name}' is required"), 400)
        return value.strip(), None

    @app.get("/")
    def index():
        return send_from_directory(STATIC, "index.html")

    @app.get("/api/status")
    def status():
        return jsonify(specs=hardware.get_specs(), alerts=system.daemon.get_alerts(),
                       tasks=system.tasks.list(), auth_required=bool(token))

    @app.post("/api/chat")
    def chat():
        message, err = body_field("message")
        if err:
            return err
        with ai_lock:
            reply = system.kernel.run_command(message)
        return jsonify(reply=reply, tool_failed=system.kernel.last_run_failed)

    @app.get("/api/tasks")
    def list_tasks():
        return jsonify(tasks=system.tasks.list())

    @app.post("/api/tasks")
    def add_task():
        desc, err = body_field("task")
        if err:
            return err
        priority = (request.get_json(silent=True) or {}).get("priority", "Medium")
        if priority not in ("Low", "Medium", "High"):
            return jsonify(error="priority must be Low, Medium or High"), 400
        return jsonify(message=system.tasks.add(desc, priority)), 201

    @app.post("/api/tasks/<int:task_id>/complete")
    def complete_task(task_id):
        try:
            return jsonify(message=system.tasks.complete(task_id))
        except LookupError as e:
            return jsonify(error=str(e)), 404

    @app.delete("/api/tasks/<int:task_id>")
    def delete_task(task_id):
        try:
            return jsonify(message=system.tasks.delete(task_id))
        except LookupError as e:
            return jsonify(error=str(e)), 404

    @app.post("/api/agent/plan")
    def agent_plan():
        goal, err = body_field("goal")
        if err:
            return err
        with ai_lock:
            steps = system.agent.plan(goal)
        return jsonify(goal=goal, steps=steps)

    @app.post("/api/agent/run")
    def agent_run():
        goal, err = body_field("goal")
        if err:
            return err
        steps = (request.get_json(silent=True) or {}).get("steps")
        if not isinstance(steps, list) or not steps:
            return jsonify(error="'steps' must be a non-empty list (call /api/agent/plan first)"), 400
        log_steps = []
        with ai_lock:
            summary = system.agent.run(
                goal, steps=steps,
                on_step=lambda i, n, step, result: log_steps.append(
                    {"step": step, "result": result,
                     "ok": not result.startswith(("FAILED", "SKIPPED"))}))
        return jsonify(summary=summary, steps=log_steps)

    return app
