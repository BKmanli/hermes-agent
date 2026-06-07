#!/usr/bin/env python3
"""
Clarify Tool Module - Interactive Clarifying Questions

Allows the agent to present structured multiple-choice questions or open-ended
prompts to the user. In CLI mode, choices are navigable with arrow keys. On
messaging platforms, choices are rendered as a numbered list.

The actual user-interaction logic lives in the platform layer (cli.py for CLI,
gateway/run.py for messaging). This module defines the schema, validation, and
a thin dispatcher that delegates to a platform-provided callback.
"""

import json
from typing import List, Optional, Callable


# Maximum number of predefined choices the agent can offer.
# A 5th "Other (type your answer)" option is always appended by the UI.
MAX_CHOICES = 4


def clarify_tool(
    question: str,
    choices: Optional[List[str]] = None,
    callback: Optional[Callable] = None,
    default_choice: Optional[str] = None,
) -> str:
    """
    Ask the user a question, optionally with multiple-choice options.

    Args:
        question: The question text to present.
        choices:  Up to 4 predefined answer choices. When omitted the
                  question is purely open-ended.
        callback: Platform-provided function that handles the actual UI
                  interaction. Signature: callback(question, choices) -> str.
                  Injected by the agent runner (cli.py / gateway).
        default_choice: Optional fallback to use when the callback reports
                        a no-response timeout. May be an exact choice string
                        or a 1-based numeric index into choices.

    Returns:
        JSON string with the user's response.
    """
    if not question or not question.strip():
        return tool_error("Question text is required.")

    question = question.strip()

    # Validate and trim choices
    if choices is not None:
        if not isinstance(choices, list):
            return tool_error("choices must be a list of strings.")
        choices = [str(c).strip() for c in choices if str(c).strip()]
        if len(choices) > MAX_CHOICES:
            choices = choices[:MAX_CHOICES]
        if not choices:
            choices = None  # empty list → open-ended

    normalized_default = _normalize_default_choice(default_choice, choices)
    if default_choice is not None and normalized_default is None:
        return tool_error("default_choice must match one of choices or be a valid 1-based choice index.")

    if callback is None:
        return json.dumps(
            {"error": "Clarify tool is not available in this execution context."},
            ensure_ascii=False,
        )

    try:
        user_response = callback(question, choices)
    except Exception as exc:
        return json.dumps(
            {"error": f"Failed to get user input: {exc}"},
            ensure_ascii=False,
        )

    raw_response = str(user_response).strip()
    default_applied = False
    response = raw_response
    if normalized_default is not None and _is_no_response_sentinel(raw_response):
        response = normalized_default
        default_applied = True

    payload = {
        "question": question,
        "choices_offered": choices,
        "user_response": response,
    }
    if normalized_default is not None:
        payload["default_choice"] = normalized_default
        payload["default_applied"] = default_applied
        if default_applied:
            payload["raw_user_response"] = raw_response
    return json.dumps(payload, ensure_ascii=False)


def _normalize_default_choice(default_choice: Optional[str], choices: Optional[List[str]]) -> Optional[str]:
    """Normalize a default choice string/index against the offered choices."""
    if default_choice is None:
        return None
    default_text = str(default_choice).strip()
    if not default_text:
        return None
    if choices:
        if default_text.isdigit():
            index = int(default_text) - 1
            if 0 <= index < len(choices):
                return choices[index]
            return None
        for choice in choices:
            if choice == default_text or choice.casefold() == default_text.casefold():
                return choice
        return None
    return default_text


def _is_no_response_sentinel(response: str) -> bool:
    """Return True for gateway/CLI sentinels that mean the user stayed silent."""
    normalized = response.strip().casefold()
    return normalized.startswith("[user did not respond within")


def check_clarify_requirements() -> bool:
    """Clarify tool has no external requirements -- always available."""
    return True


# =============================================================================
# OpenAI Function-Calling Schema
# =============================================================================

CLARIFY_SCHEMA = {
    "name": "clarify",
    "description": (
        "Ask the user a question when you need clarification, feedback, or a "
        "decision before proceeding. Supports two modes:\n\n"
        "1. **Multiple choice** — provide up to 4 choices. The user picks one "
        "or types their own answer via a 5th 'Other' option.\n"
        "2. **Open-ended** — omit choices entirely. The user types a free-form "
        "response.\n\n"
        "Use this tool when:\n"
        "- The task is ambiguous and you need the user to choose an approach\n"
        "- You want post-task feedback ('How did that work out?')\n"
        "- You want to offer to save a skill or update memory\n"
        "- A decision has meaningful trade-offs the user should weigh in on\n\n"
        "Do NOT use this tool for simple yes/no confirmation of dangerous "
        "commands (the terminal tool handles that). Prefer making a reasonable "
        "default choice yourself when the decision is low-stakes."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The question to present to the user.",
            },
            "choices": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": MAX_CHOICES,
                "description": (
                    "Up to 4 answer choices. Omit this parameter entirely to "
                    "ask an open-ended question. When provided, the UI "
                    "automatically appends an 'Other (type your answer)' option."
                ),
            },
            "default_choice": {
                "type": "string",
                "description": (
                    "Optional fallback to use if the user does not respond before "
                    "the platform clarify timeout. Must match one of choices or be "
                    "a 1-based choice index. Use only for low-risk defaults where "
                    "proceeding is better than waiting forever."
                ),
            },
        },
        "required": ["question"],
    },
}


# --- Registry ---
from tools.registry import registry, tool_error

registry.register(
    name="clarify",
    toolset="clarify",
    schema=CLARIFY_SCHEMA,
    handler=lambda args, **kw: clarify_tool(
        question=args.get("question", ""),
        choices=args.get("choices"),
        default_choice=args.get("default_choice"),
        callback=kw.get("callback")),
    check_fn=check_clarify_requirements,
    emoji="❓",
)
