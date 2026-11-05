"""Tests of the conversation reader: messages, answers and previews (no network)."""

import json

from dashboard.conversations import (
    PREVIEW_CHARS,
    content_text,
    detail,
    last_user_text,
    output_text,
    parse_messages,
    preview,
    summarize,
)

INPUT = json.dumps([
    {"role": "system", "content": "Você é um assistente."},
    {"role": "user", "content": "Analise este contrato."},
])


def test_messages_are_read_from_the_json_text_of_the_input():
    messages = parse_messages(INPUT)
    assert [item["role"] for item in messages] == ["system", "user"]


def test_invalid_or_non_chat_input_gives_no_messages():
    assert parse_messages("não é json") == []
    assert parse_messages({"prompt": "x"}) == []
    assert parse_messages(None) == []


def test_the_question_is_the_last_user_message():
    messages = parse_messages(INPUT)
    assert last_user_text(messages) == "Analise este contrato."


def test_content_parts_are_joined_as_text():
    parts = [{"type": "text", "text": "Olá"}, {"type": "image_url", "image_url": {}}, {"type": "text", "text": "mundo"}]
    assert content_text(parts) == "Olá\nmundo"


def test_output_is_read_from_a_message_dict_or_plain_text():
    assert output_text(json.dumps({"role": "assistant", "content": "Resposta."})) == "Resposta."
    assert output_text("texto simples") == "texto simples"
    assert output_text({"message": {"content": "Aninhada."}}) == "Aninhada."


def test_long_previews_are_cut_with_an_ellipsis():
    text = "a" * (PREVIEW_CHARS + 50)
    cut = preview(text)
    assert len(cut) == PREVIEW_CHARS
    assert cut.endswith("…")
    assert preview("curto") == "curto"


def test_summary_keeps_the_student_name_and_the_previews():
    observation = {
        "id": "obs-1",
        "startTime": "2026-11-02T10:00:00Z",
        "userId": "1045004",
        "input": INPUT,
        "output": json.dumps({"role": "assistant", "content": "Parece um contrato de locação."}),
    }
    row = summarize(observation, {"1045004": "Aluno Teste"})
    assert row["id"] == "obs-1"
    assert row["name"] == "Aluno Teste"
    assert row["question"] == "Analise este contrato."
    assert row["answer"] == "Parece um contrato de locação."


def test_detail_has_every_message_and_the_full_answer():
    observation = {"id": "obs-2", "input": INPUT, "output": "Resposta completa."}
    result = detail(observation)
    assert result["id"] == "obs-2"
    assert result["messages"][1] == {"role": "user", "content": "Analise este contrato."}
    assert result["answer"] == "Resposta completa."
