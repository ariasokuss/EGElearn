import pytest

from src.roadmap.pqg_seeder import (
    parse_question_types_md,
    parse_prompt_file,
    slugify_service_name,
    _extract_variables,
)


def test_parse_question_types_md():
    md = """\
| Label | Key | Points |
|-------|-----|--------|
| Section A questions | section_a | 5 |
| 5 mark questions | five_mark | 5 |
| 8 mark questions | eight_mark | 8 |
"""
    result = parse_question_types_md(md)
    assert len(result) == 3
    assert result[0] == {"label": "Section A questions", "key": "section_a", "points": 5}
    assert result[1] == {"label": "5 mark questions", "key": "five_mark", "points": 5}
    assert result[2] == {"label": "8 mark questions", "key": "eight_mark", "points": 8}


def test_parse_question_types_md_empty():
    assert parse_question_types_md("") == []


def test_parse_question_types_md_no_data_rows():
    md = "| Label | Key | Points |\n|---|---|---|"
    assert parse_question_types_md(md) == []


def test_parse_prompt_file():
    content = """\
---system---
You are an expert examiner.

---user---
Topic: {topic_name}

{lesson_content}
"""
    system, user = parse_prompt_file(content)
    assert system == "You are an expert examiner."
    assert "{topic_name}" in user
    assert "{lesson_content}" in user


def test_parse_prompt_file_no_user():
    content = "---system---\nJust system content"
    system, user = parse_prompt_file(content)
    assert system == "Just system content"
    assert user == ""


def test_parse_prompt_file_no_markers():
    content = "Raw content without markers"
    system, user = parse_prompt_file(content)
    assert system == "Raw content without markers"
    assert user == ""


def test_slugify_service_name():
    assert slugify_service_name("Edexcel A-Level Economics") == "pqg-edexcel-a-level-economics"
    assert slugify_service_name("AQA A-Level Psyhology") == "pqg-aqa-a-level-psyhology"


def test_extract_variables():
    template = "Topic: {topic_name}\n\n{lesson_content}\n{topic_name}"
    result = _extract_variables(template)
    assert result == ["topic_name", "lesson_content"]


def test_extract_variables_empty():
    assert _extract_variables("no placeholders here") == []
