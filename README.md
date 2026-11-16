# AetherOS 2.1 (modular)

    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env   # then add your NEW API key
    python main.py

Agent mode: `/plan <goal>` plans the goal and asks before each step (y/n/a for all); `/auto <goal>` runs without asking. Failed steps trigger a re-plan (up to `AGENT_MAX_REPLANS`).

Data lives in `~/AetherOS` (override with `AETHER_HOME`); files the AI writes go to `~/AetherOS/workspace`.

Adding a tool: create `tools/<name>.py`, add its schema to `TOOLS` in `core/kernel.py`, and handle it in `Kernel._execute_tool`.

## Memory

- **Short-term:** each chat session keeps its history (last `HISTORY_MESSAGES`, default 12, are sent to the model). Terminal and web UI have separate sessions. Agent steps run statelessly.
- **Long-term:** facts you ask it to remember (importance 0.9), task and file events (0.5-0.6) and automatic summaries (0.6). Raw chat is no longer logged as memory.
- **Retrieval:** relevance gate on similarity, then ranked by similarity + recency (half-life `MEMORY_HALF_LIFE_DAYS`) + importance; weights in `config.py`.
- **Dedupe:** near-duplicates (>= `MEMORY_DEDUPE_THRESHOLD`) of the same kind are merged and refreshed instead of added.
- **Consolidation:** once `CONSOLIDATE_AFTER` older messages pile up, they are summarized into one memory.
- **Control:** terminal `/memories`, `/forget <id>`, `/clear`; web sidebar has Forget buttons and New chat.
- Old databases are migrated automatically on start (past exchange logs are marked low-importance).

## Web UI

    python serve.py        # then open http://127.0.0.1:8000

Chat mode talks to the kernel. Plan mode shows the agent's proposed steps; edit them, untick any to skip, then press Run plan. The sidebar shows host stats, daemon alerts and your tasks.

It listens on localhost only. To expose it, set `AETHER_HOST` **and** `AETHER_API_TOKEN` (the server refuses to start on a non-local address without a token); put it behind HTTPS if it leaves your machine.

API: `GET /api/status`, `POST /api/chat {message}`, `GET|POST /api/tasks`, `POST /api/tasks/<id>/complete`, `DELETE /api/tasks/<id>`, `POST /api/agent/plan {goal}`, `POST /api/agent/run {goal, steps}`.

## Tests

    python -m unittest discover -v
