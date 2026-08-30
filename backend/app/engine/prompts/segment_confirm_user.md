Beat so far (unclosed):
{{ beat_text }}

Given this transcript plus the fact a boundary signal fired (silence/speaker change/buffer full), decide: has the discussion reached a natural closing point for a beat?
Return JSON: {"closed": bool, "reason": "silence"|"topic_shift"|"closing_cue"|"buffer_full"|null}
