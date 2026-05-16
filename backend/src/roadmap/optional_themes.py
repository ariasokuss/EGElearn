"""Optional exam theme configurations keyed by folder name.

Each entry has:
  title       – display name for the paper
  exam_date   – ISO datetime ending in .929929Z (sentinel to distinguish from user exams)
  blocks      – list of blocks; user picks one option per block.
                Each option is a plain str when display name == DB section name,
                or {"name": str, "backend_name": str} when they differ.
"""
from typing import TypedDict


class _OptionDict(TypedDict):
    name: str
    backend_name: str


class _ThemeConfig(TypedDict, total=False):
    title: str
    exam_date: str
    blocks: list[list[str | _OptionDict]]
    base_themes: list[int]  # 1-based level-1 section positions always part of the paper


OPTIONAL_THEMES: dict[str, _ThemeConfig] = {
    "AQA A-Level Psychology": {
        "title": "Paper 3",
        "exam_date": "2026-05-28T08:00:00.929929Z",
        "blocks": [
            ["3.2 Relationships", "3.3 Gender", "3.4 Cognition and Development"],
            ["3.5 Schizophrenia", "3.6 Eating Behaviour", "3.7 Stress"],
            ["3.8 Aggression", "3.9 Offending Behaviour", "3.10 Addiction"],
        ],
    },
    "AQA A-Level Physics": {
        "title": "Paper 3 Practical Skills and Option Topic",
        "exam_date": "2026-06-08T09:00:00.929929+01:00",
        "base_themes": [1, 2, 3, 4, 5, 6, 7, 8],
        "blocks": [
            [
                {"name": "Astrophysics", "backend_name": "Option A: Astrophysics"},
                {"name": "Medical physics", "backend_name": "Option B: Medical Physics"},
                {"name": "Engineering physics", "backend_name": "Option C: Engineering Physics"},
                {"name": "Turning points", "backend_name": "Option D: Turning Points in Physics"},
                {"name": "Electronics", "backend_name": "Option E: Electronics"},
            ]
        ],
    },
    "AQA A-Level Sociology": {
        "title": "Paper 2",
        "exam_date": "2026-05-28T08:00:00.929929Z",
        "blocks": [
            [
                "2.1 Culture and Identity",
                "2.2 Families and Households",
                "2.3 Health",
                "2.4 Work, Poverty and Welfare",
            ],
            [
                "2.5 Beliefs in Society",
                "2.6 Global Development",
                "2.7 The Media",
                "2.8 Stratification and Differentiation",
            ],
        ],
    },
}
