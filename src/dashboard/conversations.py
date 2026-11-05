"""Reads the prompts and completions of the generations (pure functions)."""

import json
from typing import Any

PREVIEW_CHARS = 220


def parse_messages(raw: Any) -> list[dict[str, Any]]:
    """Read the chat messages sent to the model.

    Parameters
    ----------
    raw : Any
        Input of the generation: a JSON text with a list of messages, or a list.

    Returns
    -------
    list[dict[str, Any]]
        Messages with role and content; empty when the input is not a chat.
    """
    value = raw
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except ValueError:
            return []
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def content_text(content: Any) -> str:
    """Text of a message content, which may be a string or a list of parts.

    Parameters
    ----------
    content : Any
        Content of a message.

    Returns
    -------
    str
        The plain text of the content.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(part.get("text", ""))
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    return ""


def last_user_text(messages: list[dict[str, Any]]) -> str:
    """Text of the last message written by the user.

    Parameters
    ----------
    messages : list[dict[str, Any]]
        Messages sent to the model.

    Returns
    -------
    str
        Text of the last user message, or an empty string.
    """
    for message in reversed(messages):
        if message.get("role") == "user":
            return content_text(message.get("content"))
    return ""


def output_text(raw: Any) -> str:
    """Text of the model answer.

    Parameters
    ----------
    raw : Any
        Output of the generation: a JSON text with a message, or plain text.

    Returns
    -------
    str
        The text of the answer.
    """
    value = raw
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except ValueError:
            return raw
    if isinstance(value, dict):
        if "content" in value:
            return content_text(value["content"])
        if "message" in value and isinstance(value["message"], dict):
            return content_text(value["message"].get("content"))
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return content_text(value)


def preview(text: str, limit: int = PREVIEW_CHARS) -> str:
    """Shorten a text for the list, keeping the start of it.

    Parameters
    ----------
    text : str
        Full text.
    limit : int
        Longest length of the preview, in characters.

    Returns
    -------
    str
        The text, cut with an ellipsis when it is longer than the limit.
    """
    return text if len(text) <= limit else text[: limit - 1] + "…"


def summarize(observation: dict[str, Any], student_names: dict[str, str]) -> dict[str, Any]:
    """Build the row of one generation for the list of conversations.

    Parameters
    ----------
    observation : dict[str, Any]
        Generation as returned by the observations API.
    student_names : dict[str, str]
        Name of each registration number.

    Returns
    -------
    dict[str, Any]
        Id, time, user, name, model, question and answer previews.
    """
    user_id = observation.get("userId")
    question = last_user_text(parse_messages(observation.get("input")))
    answer = output_text(observation.get("output"))
    return {
        "id": observation.get("id"),
        "time": observation.get("startTime"),
        "user_id": user_id,
        "name": student_names.get(str(user_id)) if user_id else None,
        "model": observation.get("model") or observation.get("providedModelName"),
        "question": preview(question),
        "answer": preview(answer),
    }


def detail(observation: dict[str, Any]) -> dict[str, Any]:
    """Build the full conversation of one generation.

    Parameters
    ----------
    observation : dict[str, Any]
        Generation as returned by the observations API.

    Returns
    -------
    dict[str, Any]
        All messages sent to the model and the full answer.
    """
    return {
        "id": observation.get("id"),
        "messages": [
            {"role": str(item.get("role", "")), "content": content_text(item.get("content"))}
            for item in parse_messages(observation.get("input"))
        ],
        "answer": output_text(observation.get("output")),
    }
