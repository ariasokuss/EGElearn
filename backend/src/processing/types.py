"""Dataclasses for the document processing pipeline."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class Window:
    """A sliding-window segment of the source markdown."""

    text: str
    token_count: int
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class ClusterSegment:
    """A reference to a line range inside a specific window."""

    window_uuid: str
    start_line: int  # 1-based, inclusive
    end_line: int  # 1-based, inclusive
    preview: str = ""


@dataclass
class SemanticChunk:
    """An individual chunk produced by embedding-based similarity splitting."""

    text: str
    page: int
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class TopicCluster:
    """A thematic cluster identified by the LLM from one or more windows."""

    topic_description: str
    segments: list[ClusterSegment] = field(default_factory=list)
    window_uuids: list[str] = field(default_factory=list)
    text: str = ""
    token_count: int = 0
    content_type: str = "study"  # "study" | "admin" | "trash"
    content_quality: int = 3  # 1-5
    document_id: str = ""
    document_pages: list[int] = field(default_factory=list)
    semantic_chunks: list[SemanticChunk] = field(default_factory=list)
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def num_windows(self) -> int:
        if self.window_uuids:
            return len(self.window_uuids)
        return len({s.window_uuid for s in self.segments})


@dataclass
class MegaCluster:
    """A cross-document group of semantically similar clusters."""

    name: str
    description: str
    clusters: list[TopicCluster]
    document_ids: list[str] = field(default_factory=list)
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def cluster_uuids(self) -> list[str]:
        return [c.uuid for c in self.clusters]


@dataclass
class PipelineResult:
    """Output of the full processing pipeline for a single document."""

    clusters: list[TopicCluster]
    megaclusters: list[MegaCluster]
    windows: list[Window]
    total_tokens: int
