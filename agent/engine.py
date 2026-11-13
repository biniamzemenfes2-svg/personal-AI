"""Agent engine: plan -> (approve) -> execute -> re-plan on failure -> summarize."""
import json
import logging

import config

log = logging.getLogger("aetheros.agent")

PLAN_PROMPT = (
    "You are the planning module of AetherOS. Break the user's goal into a short, "
    "ordered list of concrete steps (at most {max_steps}). Each step must be doable "
    "with the available tools: hardware stats, reading/writing/listing files in the "
    "workspace, managing tasks, and saving/recalling memory. Do not include steps "
    "that need anything else. Reply with JSON only: {{\"steps\": [\"...\", \"...\"]}}"
)

REPLAN_PROMPT = (
    "A step of the plan failed. Given the goal, what has been done so far and the "
    "failure, write a revised list of the REMAINING steps only (at most {max_steps}). "
    "Do not repeat completed steps. If the goal can't be reached with the available "
    "tools, return an empty list. Reply with JSON only: {{\"steps\": [...]}}"
)


class AgentEngine:
    def __init__(self, client, kernel):
        self.client = client
        self.kernel = kernel

    def _ask_steps(self, system: str, user: str):
        resp = self.client.chat.completions.create(
            model=config.MODEL_NAME,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_object"},
        )
        try:
            steps = json.loads(resp.choices[0].message.content)["steps"]
            steps = [str(s).strip() for s in steps if str(s).strip()]
        except (json.JSONDecodeError, KeyError, TypeError):
            log.warning("Planner returned unparseable output")
            return None
        return steps[: config.AGENT_MAX_STEPS]

    def plan(self, goal: str):
        steps = self._ask_steps(PLAN_PROMPT.format(max_steps=config.AGENT_MAX_STEPS), goal)
        return steps or [goal][: config.AGENT_MAX_STEPS]

    def replan(self, goal, results, failed_step, error):
        done = "\n".join(f"- {s} -> {r}" for s, r in results) or "(nothing yet)"
        user = f"Goal: {goal}\n\nDone so far:\n{done}\n\nFailed step: {failed_step}\nError: {error}"
        return self._ask_steps(REPLAN_PROMPT.format(max_steps=config.AGENT_MAX_STEPS), user) or []

    def run(self, goal: str, on_plan=None, on_step=None, approve=None, steps=None) -> str:
        """approve(i, total, step) -> bool lets the caller veto each step (None = auto).
        steps: optional pre-approved plan (e.g. edited in the web UI); skips planning."""
        queue = [str(x).strip() for x in steps if str(x).strip()][: config.AGENT_MAX_STEPS] if steps else self.plan(goal)
        if on_plan:
            on_plan(list(queue))

        results, replans, i = [], 0, 0
        while queue:
            step = queue.pop(0)
            i += 1
            total = i + len(queue)

            if approve and not approve(i, total, step):
                results.append((step, "SKIPPED by user"))
                if on_step:
                    on_step(i, total, step, "SKIPPED by user")
                continue

            history = "\n".join(f"Step result: {s} -> {r}" for s, r in results)
            prompt = (
                f"Overall goal: {goal}\n"
                f"Remaining plan: {json.dumps([step] + queue)}\n"
                f"{history}\n"
                f"Now carry out only this step: {step}"
            )
            try:
                result = self.kernel.run_command(prompt)
                failed = bool(getattr(self.kernel, "last_run_failed", False))
                if failed:
                    result = f"FAILED: a tool call failed and was not recovered. {result}"
            except Exception as e:
                log.exception("Step failed: %s", step)
                result, failed = f"FAILED: {e}", True
            results.append((step, result))
            if on_step:
                on_step(i, total, step, result)

            if failed and replans < config.AGENT_MAX_REPLANS:
                replans += 1
                queue = self.replan(goal, results, step, result)
                if on_plan:
                    on_plan(list(queue), revised=True)

        return self._summarize(goal, results)

    def _summarize(self, goal, results) -> str:
        report = "\n".join(f"{n}. {s}\n   -> {r}" for n, (s, r) in enumerate(results, 1))
        resp = self.client.chat.completions.create(
            model=config.MODEL_NAME,
            messages=[
                {"role": "system", "content": "Summarize what was accomplished for the goal. "
                 "Be honest about any failed, skipped or incomplete steps. Be concise."},
                {"role": "user", "content": f"Goal: {goal}\n\nSteps and results:\n{report}"},
            ],
        )
        return resp.choices[0].message.content or ""
