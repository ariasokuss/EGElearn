"""Processing pipeline orchestrator and Qdrant vector store upload.

Ties together all stages: splitting → clustering → semantic chunking →
megaclustering → embedding → Qdrant upload.
"""

from __future__ import annotations

import logging
import uuid

from src.config import ProcessingSettings
from src.core.yandex_gpt import YandexGPTLLMGateway
from src.prompts.manager import PromptManager
from src.core.qdrant import (
    ChunkPayload,
    ChunkPoint,
    ClusterPayload,
    ClusterPoint,
    QdrantStore,
)
from src.core.voyage import VoyageEmbeddingService
from src.processing.chunking import (
    SemanticChunkingService,
    TopicClusteringService,
    build_page_map,
    count_tokens,
    extract_text_by_lines,
    get_pages_for_line_range,
    insert_line_markers,
    split_to_windows,
)
from src.processing.megaclustering import (
    _derive_megacluster_description,
    _derive_megacluster_name,
    identify_megaclusters,
)
from src.processing.models import ProcessingJobStatus
from src.processing.service import save_megaclusters, update_job_status
from src.processing.types import PipelineResult, TopicCluster, Window

logger = logging.getLogger(__name__)


def _dominant_content_type(clusters: list[TopicCluster]) -> str:
    """Return the most common content_type among *clusters*."""
    from collections import Counter

    if not clusters:
        return "study"
    counts = Counter(c.content_type for c in clusters)
    return counts.most_common(1)[0][0]


def _populate_cluster_text(clusters: list[TopicCluster], windows: list[Window]) -> None:
    """Fill each cluster's ``text`` and ``token_count`` from window segments."""
    window_by_uuid = {w.uuid: w for w in windows}
    for cluster in clusters:
        parts: list[str] = []
        segs = cluster.segments or []
        if segs:
            for seg in segs:
                w = window_by_uuid.get(seg.window_uuid)
                if not w:
                    continue
                marked = insert_line_markers(w.text, start_at=1)
                parts.append(
                    extract_text_by_lines(marked, seg.start_line, seg.end_line)
                )
        else:
            for wu in cluster.window_uuids:
                w = window_by_uuid.get(wu)
                if w:
                    parts.append(w.text)
        text = "\n\n".join(p for p in parts if p)
        cluster.text = text
        cluster.token_count = count_tokens(text)


def _populate_cluster_pages(
    clusters: list[TopicCluster],
    windows: list[Window],
    text: str,
) -> None:
    """Fill each cluster's ``document_pages`` from ``[PAGE N]`` markers."""
    page_map = build_page_map(text)
    if not page_map:
        return

    window_line_offsets: dict[str, int] = {}
    offset = 0
    for w in windows:
        window_line_offsets[w.uuid] = offset
        offset += w.text.count("\n") + 1

    for cluster in clusters:
        pages: set[int] = set()
        for seg in cluster.segments:
            w_offset = window_line_offsets.get(seg.window_uuid, 0)
            doc_start = w_offset + seg.start_line
            doc_end = w_offset + seg.end_line
            pages.update(get_pages_for_line_range(page_map, doc_start, doc_end))
        cluster.document_pages = sorted(pages)


async def _store_results_to_qdrant(
    result: PipelineResult,
    user_id: str,
    folder_id: str,
    document_id: str,
    qdrant: QdrantStore,
    voyage: VoyageEmbeddingService,
) -> None:
    """Delete old vectors for the document, embed new chunks/clusters, upload to Qdrant."""

    await qdrant.delete_by_document(user_id, document_id)

    cluster_to_mega: dict[str, str] = {}
    for mc in result.megaclusters:
        for c in mc.clusters:
            cluster_to_mega[c.uuid] = mc.uuid

    chunk_texts: list[str] = []
    chunk_payloads: list[ChunkPayload] = []
    for cluster in result.clusters:
        mc_id = cluster_to_mega.get(cluster.uuid, "")
        ct = cluster.content_type
        for sc in cluster.semantic_chunks:
            if not sc.text.strip():
                continue
            chunk_texts.append(sc.text)
            chunk_payloads.append(
                ChunkPayload(
                    user_id=user_id,
                    folder_id=folder_id,
                    document_id=document_id,
                    cluster_id=cluster.uuid,
                    megacluster_id=mc_id,
                    page=sc.page,
                    content=sc.text,
                    content_type=ct,
                    content_quality=cluster.content_quality,
                )
            )

    if chunk_texts:
        chunk_embeddings = await voyage.embed_batch(chunk_texts, input_type="document")
        chunk_points = [
            ChunkPoint(
                chunk_id=uuid.uuid4(),
                vector=emb,
                **payload.model_dump(),
            )
            for emb, payload in zip(chunk_embeddings, chunk_payloads)
        ]
        await qdrant.upload_chunks(chunk_points)
        logger.info(
            "Uploaded %d chunks to Qdrant for document %s",
            len(chunk_points),
            document_id,
        )

    cluster_texts: list[str] = []
    cluster_payloads: list[ClusterPayload] = []
    for cluster in result.clusters:
        desc = (cluster.topic_description or "").strip()
        if not desc:
            continue
        mc_id = cluster_to_mega.get(cluster.uuid, "")
        ct = cluster.content_type
        cluster_texts.append(desc)
        cluster_payloads.append(
            ClusterPayload(
                user_id=user_id,
                folder_id=folder_id,
                document_id=document_id,
                megacluster_id=mc_id,
                description=desc,
                pages=cluster.document_pages,
                content=cluster.text,
                content_type=ct,
                content_quality=cluster.content_quality,
            )
        )

    if cluster_texts:
        cluster_embeddings = await voyage.embed_batch(
            cluster_texts, input_type="document"
        )
        cluster_points = [
            ClusterPoint(
                cluster_id=uuid.uuid4(),
                vector=emb,
                **payload.model_dump(),
            )
            for emb, payload in zip(cluster_embeddings, cluster_payloads)
        ]
        await qdrant.upload_clusters(cluster_points)
        logger.info(
            "Uploaded %d clusters to Qdrant for document %s",
            len(cluster_points),
            document_id,
        )


async def run_pipeline(
    *,
    markdown: str,
    user_id: str,
    folder_id: str,
    document_id: str,
    qdrant: QdrantStore,
    voyage: VoyageEmbeddingService,
    llm: YandexGPTLLMGateway,
    session_factory,
    job_id: uuid.UUID,
    settings: ProcessingSettings,
    prompt_manager: PromptManager | None = None,
) -> PipelineResult:
    """Run the full chunking/clustering/embedding pipeline on markdown text.

    Called by the processing worker after markdown conversion is complete.
    """
    chunking = settings.chunking

    async with session_factory() as session:
        await update_job_status(session, job_id, ProcessingJobStatus.splitting)

    windows = split_to_windows(
        markdown,
        max_tokens=chunking.window_max_tokens,
        encoding=chunking.tiktoken_encoding,
    )
    logger.info(
        "Split document %s into %d windows (%d total tokens)",
        document_id,
        len(windows),
        sum(w.token_count for w in windows),
    )

    async with session_factory() as session:
        await update_job_status(session, job_id, ProcessingJobStatus.clustering)

    clustering_svc = TopicClusteringService(llm, model=chunking.clustering_model, prompt_manager=prompt_manager)
    clusters = await clustering_svc.identify_clusters(
        windows,
        max_retries=chunking.clustering_max_retries,
    )

    _populate_cluster_text(clusters, windows)
    _populate_cluster_pages(clusters, windows, markdown)
    logger.info(
        "Identified %d topic clusters for document %s", len(clusters), document_id
    )

    semantic_svc = SemanticChunkingService(
        voyage,
        percentile=chunking.semantic_percentile_threshold,
        min_segments=chunking.min_segments_for_similarity,
    )
    for cluster in clusters:
        if not (cluster.text or "").strip():
            continue
        pages = cluster.document_pages or [1]
        try:
            cluster.semantic_chunks = await semantic_svc.chunk_cluster(
                cluster.text, pages
            )
        except Exception:
            logger.exception(
                "Semantic chunking failed for cluster %s",
                cluster.uuid[:8],
            )
            cluster.semantic_chunks = []

    total_chunks = sum(len(c.semantic_chunks) for c in clusters)
    logger.info(
        "Produced %d semantic chunks for document %s", total_chunks, document_id
    )

    megaclusters = []
    cluster_sources: dict[str, str] = {c.uuid: document_id for c in clusters}
    if chunking.megaclustering_enabled:
        existing_clusters = await _load_existing_folder_clusters(
            qdrant,
            user_id,
            folder_id,
            exclude_document_id=document_id,
        )
        logger.info(
            "Loaded %d existing clusters from %d other documents for megaclustering",
            len(existing_clusters),
            len({c.document_id for c in existing_clusters}),
        )
        all_clusters_for_mega = existing_clusters + clusters
        for c in existing_clusters:
            cluster_sources[c.uuid] = c.document_id

        if len(set(cluster_sources.values())) >= 2:
            megaclusters = await identify_megaclusters(
                all_clusters_for_mega,
                cluster_sources,
                llm,
                voyage,
                prompt_manager=prompt_manager,
                model=chunking.clustering_model,
                centroid_sim_threshold=chunking.centroid_sim_threshold,
                chunk_sim_threshold=chunking.chunk_chunk_sim_threshold,
                borderline_low=chunking.centroid_borderline_low,
                borderline_high=chunking.centroid_borderline_high,
                candidate_centroid_floor=chunking.candidate_centroid_floor,
                top_neighbors_per_cluster=chunking.top_neighbors_per_cluster,
            )
        else:
            megaclusters = [_wrap_single_cluster(c, document_id) for c in clusters]
    else:
        megaclusters = [_wrap_single_cluster(c, document_id) for c in clusters]

    logger.info("Built %d megaclusters for document %s", len(megaclusters), document_id)

    # Persist megaclusters to PostgreSQL.
    mc_records = [
        {
            "name": mc.name,
            "description": mc.description,
            "content_type": _dominant_content_type(mc.clusters),
            "document_ids": mc.document_ids
            or [cluster_sources.get(c.uuid, "") for c in mc.clusters],
            "cluster_uuids": mc.cluster_uuids,
        }
        for mc in megaclusters
    ]
    async with session_factory() as session:
        await save_megaclusters(session, uuid.UUID(folder_id), mc_records)

    result = PipelineResult(
        clusters=clusters,
        megaclusters=megaclusters,
        windows=windows,
        total_tokens=sum(w.token_count for w in windows),
    )

    async with session_factory() as session:
        await update_job_status(session, job_id, ProcessingJobStatus.embedding)

    await _store_results_to_qdrant(
        result,
        user_id=user_id,
        folder_id=folder_id,
        document_id=document_id,
        qdrant=qdrant,
        voyage=voyage,
    )

    return result


def _wrap_single_cluster(c: TopicCluster, document_id: str):
    """Wrap a single cluster into its own megacluster."""
    from src.processing.types import MegaCluster

    return MegaCluster(
        name=_derive_megacluster_name(c.topic_description),
        description=_derive_megacluster_description(c.topic_description),
        clusters=[c],
        document_ids=[document_id],
    )


async def _load_existing_folder_clusters(
    qdrant: QdrantStore,
    user_id: str,
    folder_id: str,
    *,
    exclude_document_id: str,
) -> list[TopicCluster]:
    """Load existing clusters from Qdrant for a folder, converting them to TopicCluster."""
    records, _ = await qdrant.get_clusters(
        user_id,
        folder_id=folder_id,
        limit=500,
    )

    clusters: list[TopicCluster] = []
    for rec in records:
        if rec.document_id == exclude_document_id:
            continue
        clusters.append(
            TopicCluster(
                topic_description=rec.description,
                text=rec.content,
                content_type=rec.content_type,
                content_quality=rec.content_quality,
                document_id=rec.document_id,
                document_pages=rec.pages,
                uuid=str(rec.cluster_id),
            )
        )
    return clusters
