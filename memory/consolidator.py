"""Turns old conversation messages into a durable summary memory."""
import logging

import config
from memory.vector_store import MSG_FAILED

log = logging.getLogger("aetheros.consolidator")

SUMMARY_PROMPT = (
    "Summarize the durable information in this conversation: facts about the user, their "
    "preferences, decisions made, and open tasks or goals. Omit small talk and one-off "
    "questions. Reply with 3-6 short bullet points and nothing else."
)


class Consolidator:
    def __init__(self, client, conversation, memory):
        self.client = client
        self.conversation = conversation
        self.memory = memory

    def maybe_run(self, session_id: str):
        old = self.conversation.unsummarized_outside_window(session_id, config.HISTORY_MESSAGES)
        if len(old) < config.CONSOLIDATE_AFTER:
            return None
        transcript = "\n".join(f"{role}: {content[:500]}" for _, role, content in old)
        resp = self.client.chat.completions.create(
            model=config.MODEL_NAME,
            messages=[{"role": "system", "content": SUMMARY_PROMPT},
                      {"role": "user", "content": transcript}])
        summary = (resp.choices[0].message.content or "").strip()
        if not summary:
            return None
        # Only mark messages as summarized if the summary was actually saved.
        if self.memory.store(summary, importance=0.6, kind="summary") == MSG_FAILED:
            log.warning("Could not store summary; will retry next time")
            return None
        self.conversation.mark_summarized([i for i, _, _ in old])
        return summary
