"""Use an LLM to map past paper questions to level-3 roadmap nodes."""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass

from src.core.yandex_gpt import YandexGPTLLMGateway
from src.learning.past_paper.schemas import ParsedQuestion
from src.prompts.manager import PromptManager

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)

_SYSTEM_PROMPT = """\
You are a curriculum mapping assistant.
Given a hierarchical syllabus roadmap and a numbered list of exam questions, map
each question to the most relevant lesson node(s) in the roadmap.

Rules:
- Only level-3 nodes (lessons, shown with [id: ...]) are valid targets.
- ALWAYS assign at least one node to every question — pick the closest match
  even if the fit is only approximate. An imperfect match is better than none.
- For higher-mark questions (2+ points) that span multiple topics, include
  multiple node IDs.
- Copy UUIDs EXACTLY as they appear in the [id: ...] tags — character-for-character.
- Return a JSON object where each key is the 0-based question index as a string
  and each value is a non-empty array of lesson node UUID strings.

Example output:
{
  "0": ["a1b2c3d4-e5f6-7890-abcd-ef1234567890"],
  "1": ["b2c3d4e5-...", "c3d4e5f6-..."]
}

Output ONLY the JSON object inside a ```json ... ``` code fence. No prose outside it.\
"""

_MAX_QUESTION_LEN = 400


@dataclass
class NodeInfo:
    """Plain-Python snapshot of a RoadmapNode — safe to use after DB connection is released."""

    id: uuid.UUID
    level: int
    name: str
    position: int
    parent_id: uuid.UUID | None


def _build_tree_text(nodes: list[NodeInfo]) -> str:
    """Render a flat list of NodeInfo objects into a readable hierarchical tree string."""
    children_by_parent: dict[uuid.UUID | None, list[NodeInfo]] = {}
    for n in nodes:
        children_by_parent.setdefault(n.parent_id, []).append(n)

    lines: list[str] = []

    def _walk(parent_id: uuid.UUID | None, depth: int) -> None:
        for child in sorted(
            children_by_parent.get(parent_id, []), key=lambda n: n.position
        ):
            indent = "  " * depth
            if child.level == 3:
                lines.append(
                    f"{indent}Lesson {child.position + 1}: {child.name} [id: {child.id}]"
                )
            elif child.level == 2:
                lines.append(f"{indent}Subsection {child.position + 1}: {child.name}")
                _walk(child.id, depth + 1)
            else:
                lines.append(f"{indent}Section {child.position + 1}: {child.name}")
                _walk(child.id, depth + 1)

    _walk(None, 0)
    return "\n".join(lines)


class RoadmapNodeMatcher:
    def __init__(
        self,
        llm: YandexGPTLLMGateway,
        usage_service: object | None = None,
        prompt_manager: PromptManager | None = None,
    ) -> None:
        self._llm = llm
        self._usage_service = usage_service
        self._current_user_id: object | None = None
        self._pm = prompt_manager

    async def match(
        self,
        nodes: list[NodeInfo],
        questions: list[ParsedQuestion],
    ) -> dict[int, list[uuid.UUID]]:
        """Match each question to relevant level-3 nodes.

        Returns a mapping of question index → list of node UUIDs.
        Raises on LLM failure so the caller can log it properly.
        Returns {} only for legitimate empty-input cases.
        """
        if not questions:
            logger.warning("Node matching skipped: no questions")
            return {}
        if not nodes:
            logger.warning("Node matching skipped: no roadmap nodes provided")
            return {}

        valid_ids = {str(n.id).lower() for n in nodes if n.level == 3}
        if not valid_ids:
            logger.warning(
                "Node matching skipped: %d nodes found but none are level-3 (lessons). "
                "Levels present: %s",
                len(nodes),
                sorted({n.level for n in nodes}),
            )
            return {}

        logger.info(
            "Node matching: %d questions, %d level-3 nodes available",
            len(questions),
            len(valid_ids),
        )

        tree_text = _build_tree_text(nodes)
        logger.info("Node matching tree (first 800 chars):\n%s", tree_text[:800])

        question_lines = []
        for idx, q in enumerate(questions):
            text = q.question[:_MAX_QUESTION_LEN]
            if len(q.question) > _MAX_QUESTION_LEN:
                text += "..."
            question_lines.append(f"{idx}. [points: {q.points}] {text}")
        numbered_questions = "\n".join(question_lines)

        user_content = (
            f"## Roadmap\n\n{tree_text}\n\n## Questions\n\n{numbered_questions}"
        )
        node_system = self._pm.get("past_paper", "node_matcher_system") if self._pm else _SYSTEM_PROMPT
        messages = [
            {"role": "system", "content": node_system},
            {"role": "user", "content": user_content},
        ]

        # Let exceptions propagate — caller decides whether to treat as fatal
        raw, _usage = await self._llm.chat_complete(messages)
        if self._usage_service and self._current_user_id:
            self._usage_service.log_usage_fire_and_forget(
                user_id=self._current_user_id, feature="past_paper", usage=_usage,
            )
        logger.info("Node matching LLM response (first 500 chars): %s", raw[:500])

        return _parse_match_output(raw, valid_ids, questions)


def _parse_match_output(
    raw: str,
    valid_ids: set[str],
    questions: list[ParsedQuestion],
) -> dict[int, list[uuid.UUID]]:
    match = _JSON_FENCE_RE.search(raw)
    json_str = match.group(1).strip() if match else raw.strip()

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        logger.error(
            "Node matching: LLM returned invalid JSON: %s\nRaw: %s", exc, raw[:300]
        )
        return {}

    if not isinstance(data, dict):
        logger.error(
            "Node matching: expected JSON object, got %s. Raw: %s",
            type(data).__name__,
            raw[:300],
        )
        return {}

    result: dict[int, list[uuid.UUID]] = {}
    for idx in range(len(questions)):
        raw_list = data.get(str(idx))

        if not raw_list or not isinstance(raw_list, list):
            result[idx] = []
            continue

        parsed_ids: list[uuid.UUID] = []
        for val in raw_list:
            if not isinstance(val, str):
                logger.warning("Node matching q%d: non-string value %r", idx, val)
                continue
            normalized = val.lower().strip()
            if normalized not in valid_ids:
                logger.warning(
                    "Node matching q%d: LLM returned id %r which is not in the valid set "
                    "(possible hallucination). Valid ids sample: %s",
                    idx,
                    val,
                    list(valid_ids)[:3],
                )
                continue
            try:
                parsed_ids.append(uuid.UUID(val))
            except ValueError:
                logger.warning("Node matching q%d: could not parse UUID %r", idx, val)

        if not parsed_ids:
            logger.warning(
                "Node matching q%d: LLM returned no valid IDs despite prompt instruction "
                "to always assign — question will have no node_ids",
                idx,
            )
        result[idx] = parsed_ids

    matched_count = sum(1 for ids in result.values() if ids)
    logger.info(
        "Node matching complete: %d/%d questions got node_ids",
        matched_count,
        len(questions),
    )
    return result
