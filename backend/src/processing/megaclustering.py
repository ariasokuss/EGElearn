"""Cross-document megaclustering with chunk-to-chunk matching and LLM verification.

Groups semantically similar clusters from different documents in the same folder.

Algorithm:
1. Embed all semantic chunks, compute cluster centroids.
2. Centroid cosine similarity ≥ threshold → connected.
3. Borderline similarity → chunk-to-chunk: compare ALL chunk pairs, max ≥ threshold → connected.
4. Build connected components (Union-Find).
5. LLM verification: YandexGPT confirms each group is about the same topic.
6. Unpaired clusters become single-cluster megaclusters.
"""

import json
import logging
import re
from collections import defaultdict

import numpy as np

from src.core.yandex_gpt import YandexGPTLLMGateway
from src.core.voyage import VoyageEmbeddingService
from src.processing.types import MegaCluster, TopicCluster
from src.prompts.manager import PromptManager

logger = logging.getLogger(__name__)


MEGACLUSTER_VERIFICATION_SYSTEM = """\
You are a document analysis assistant. You receive descriptions of clusters from \
different sources. These clusters are CANDIDATES for merging (pre-filtered by semantic similarity).

Your job: group them into megaclusters.

Rules:
1. Each cluster belongs to AT MOST one megacluster, or stays unpaired.
2. MERGE aggressively when clusters address the same broad subject, even if one \
is more introductory, more detailed, or more applied than the other.
3. Also merge when one cluster is a subtype, case study, implementation, \
formula set, or evaluation method for the other broader topic.
4. Prefer FEWER, LARGER megaclusters that feel like chapter-level roadmap nodes.
5. Do NOT merge if the topics are genuinely different and would deserve \
separate study-roadmap nodes.

Return a JSON object with key "megaclusters", a list of objects:
- "name": concise topic name (2-5 words), like a study roadmap key point
- "description": short broad theme for the megacluster (max 18 words)
- "cluster_indices": list of 0-based indices into the provided clusters

Example: {{"megaclusters": [{{"name": "VaR Calculation", "description": "VaR definition, methods and calculation approaches", \
"cluster_indices": [0, 2]}}, {{"name": "Portfolio Theory", "description": "Unpaired", "cluster_indices": [1]}}]}}

Return ONLY valid JSON, no explanation."""


def _format_verification_prompt(
    clusters: list[TopicCluster],
    cluster_sources: dict[str, str],
    pm: PromptManager | None = None,
) -> dict[str, str]:
    """Build system + user prompt for LLM verification of a candidate group."""
    lines: list[str] = []
    for i, c in enumerate(clusters):
        src = cluster_sources.get(c.uuid, "unknown")
        desc = (c.topic_description or "")[:2000]
        lines.append(f'[Cluster {i}] (from "{src}")\n{desc}')
    user = "Group these clusters into megaclusters:\n\n" + "\n\n---\n\n".join(lines)
    system = pm.get("processing", "megacluster_verification_system") if pm else MEGACLUSTER_VERIFICATION_SYSTEM
    return {"system": system, "user": user}


def _derive_megacluster_name(*candidates: str, fallback: str = "Untitled topic") -> str:
    """Build a concise roadmap-style topic name from the first non-empty candidate."""
    for candidate in candidates:
        normalized = " ".join((candidate or "").replace("\n", " ").split()).strip(
            " .,:;|-"
        )
        if not normalized:
            continue
        head = re.split(r"[.!?;:]\s+", normalized, maxsplit=1)[0]
        words = head.split()
        if len(words) > 8:
            head = " ".join(words[:8])
        if len(head) > 80:
            head = head[:80].rsplit(" ", 1)[0] or head[:80]
        if head:
            return head
    return fallback


def _derive_megacluster_description(
    *candidates: str,
    fallback: str = "Unpaired",
) -> str:
    """Pick a readable description, keeping it stable for storage/UI."""
    for candidate in candidates:
        normalized = " ".join((candidate or "").replace("\n", " ").split()).strip()
        if normalized:
            return normalized[:200]
    return fallback


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    a_arr = np.array(a)
    b_arr = np.array(b)
    denom = float(np.linalg.norm(a_arr) * np.linalg.norm(b_arr))
    if denom == 0:
        return 0.0
    return float(np.dot(a_arr, b_arr) / denom)


def _compute_centroid(embeddings: list[list[float]]) -> list[float]:
    if not embeddings:
        return []
    return np.array(embeddings).mean(axis=0).tolist()


async def _build_chunk_embeddings(
    clusters: list[TopicCluster],
    voyage: VoyageEmbeddingService,
) -> dict[str, list[float]]:
    """Embed all semantic chunks (or cluster text as fallback) and return uuid→vector map."""
    to_embed: list[tuple[str, str]] = []
    for c in clusters:
        if c.semantic_chunks:
            for sc in c.semantic_chunks:
                if sc.text.strip():
                    to_embed.append((sc.uuid, sc.text))
        elif (c.text or "").strip():
            to_embed.append((c.uuid, c.text))

    if not to_embed:
        return {}

    uuids = [uid for uid, _ in to_embed]
    texts = [t for _, t in to_embed]
    embeddings = await voyage.embed_batch(texts, input_type="document")

    return dict(zip(uuids, embeddings))


def _compute_cluster_centroids(
    clusters: list[TopicCluster],
    chunk_embeddings: dict[str, list[float]],
) -> dict[str, list[float]]:
    """Compute the centroid (mean embedding) for each cluster."""
    cluster_to_embs: dict[str, list[list[float]]] = defaultdict(list)
    for c in clusters:
        if c.semantic_chunks:
            for sc in c.semantic_chunks:
                if sc.uuid in chunk_embeddings:
                    cluster_to_embs[c.uuid].append(chunk_embeddings[sc.uuid])
        elif (c.text or "").strip() and c.uuid in chunk_embeddings:
            cluster_to_embs[c.uuid].append(chunk_embeddings[c.uuid])

    return {
        c_uid: _compute_centroid(embs)
        for c_uid, embs in cluster_to_embs.items()
        if embs
    }


def _connected_components(edges: list[tuple[str, str]]) -> list[set[str]]:
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        if x not in parent:
            parent[x] = x
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(a: str, b: str) -> None:
        pa, pb = find(a), find(b)
        if pa != pb:
            parent[pa] = pb

    for a, b in edges:
        union(a, b)

    groups: dict[str, set[str]] = {}
    for x in parent:
        root = find(x)
        groups.setdefault(root, set()).add(x)

    return list(groups.values())


def _find_candidate_groups(
    all_clusters: list[TopicCluster],
    cluster_sources: dict[str, str],
    centroids: dict[str, list[float]],
    chunk_embeddings: dict[str, list[float]],
    *,
    centroid_sim_threshold: float = 0.85,
    chunk_sim_threshold: float = 0.85,
    borderline_low: float = 0.80,
    borderline_high: float = 0.90,
    candidate_centroid_floor: float = 0.0,
    top_neighbors_per_cluster: int = 0,
) -> list[set[str]]:
    """Find groups of clusters that should be merged based on embedding similarity.

    1. Centroid similarity ≥ centroid_sim_threshold → edge.
    2. Borderline (borderline_low..borderline_high) → chunk-to-chunk:
       compare ALL chunk pairs, max ≥ chunk_sim_threshold → edge.
    3. Return connected components.
    """
    doc_by_cluster = {c.uuid: cluster_sources.get(c.uuid, "") for c in all_clusters}
    edges: list[tuple[str, str]] = []
    edge_set: set[tuple[str, str]] = set()
    candidate_pairs_by_cluster: dict[str, list[tuple[float, str]]] = defaultdict(list)
    strong_edges = 0
    borderline_edges = 0
    exploratory_edges = 0

    clusters_with_centroid = [c for c in all_clusters if c.uuid in centroids]
    for i, ca in enumerate(clusters_with_centroid):
        doc_a = doc_by_cluster[ca.uuid]
        cent_a = centroids[ca.uuid]
        for cb in clusters_with_centroid[i + 1 :]:
            doc_b = doc_by_cluster[cb.uuid]
            if doc_a == doc_b:
                continue

            sim = _cosine_similarity(cent_a, centroids[cb.uuid])
            logger.debug(
                "Centroid sim %.4f between %s (doc %s) and %s (doc %s)",
                sim,
                ca.uuid[:8],
                doc_a[:8],
                cb.uuid[:8],
                doc_b[:8],
            )
            sorted_pair = sorted((ca.uuid, cb.uuid))
            pair: tuple[str, str] = (sorted_pair[0], sorted_pair[1])

            if sim >= candidate_centroid_floor:
                candidate_pairs_by_cluster[ca.uuid].append((sim, cb.uuid))
                candidate_pairs_by_cluster[cb.uuid].append((sim, ca.uuid))

            if sim >= centroid_sim_threshold:
                logger.info(
                    "Centroid match %.4f: %s <-> %s", sim, ca.uuid[:8], cb.uuid[:8]
                )
                if pair not in edge_set:
                    edge_set.add(pair)
                    strong_edges += 1
                continue

            # Borderline → chunk-to-chunk matching
            if borderline_low <= sim <= borderline_high:
                uuids_a = _chunk_uuids_for(ca)
                uuids_b = _chunk_uuids_for(cb)
                if not uuids_a or not uuids_b:
                    continue
                embs_a = [chunk_embeddings[u] for u in uuids_a if u in chunk_embeddings]
                embs_b = [chunk_embeddings[u] for u in uuids_b if u in chunk_embeddings]
                if not embs_a or not embs_b:
                    continue
                max_sim = max(
                    _cosine_similarity(ea, eb) for ea in embs_a for eb in embs_b
                )
                logger.info(
                    "Borderline centroid %.4f, chunk-to-chunk max %.4f: %s <-> %s",
                    sim,
                    max_sim,
                    ca.uuid[:8],
                    cb.uuid[:8],
                )
                if max_sim >= chunk_sim_threshold:
                    if pair not in edge_set:
                        edge_set.add(pair)
                        borderline_edges += 1

    if top_neighbors_per_cluster > 0:
        for cluster in clusters_with_centroid:
            ranked_neighbors = sorted(
                candidate_pairs_by_cluster.get(cluster.uuid, []),
                reverse=True,
                key=lambda item: item[0],
            )
            for _, neighbor_uuid in ranked_neighbors[:top_neighbors_per_cluster]:
                _sorted_pair = sorted((cluster.uuid, neighbor_uuid))
                pair = (_sorted_pair[0], _sorted_pair[1])
                if pair in edge_set:
                    continue
                edge_set.add(pair)
                exploratory_edges += 1

    edges = list(edge_set)
    logger.info(
        "Megacluster similarity graph: clusters=%d strong_edges=%d borderline_edges=%d exploratory_edges=%d total_edges=%d thresholds=(centroid>=%.2f chunk>=%.2f borderline=%.2f..%.2f candidate_floor=%.2f top_k=%d)",
        len(clusters_with_centroid),
        strong_edges,
        borderline_edges,
        exploratory_edges,
        len(edges),
        centroid_sim_threshold,
        chunk_sim_threshold,
        borderline_low,
        borderline_high,
        candidate_centroid_floor,
        top_neighbors_per_cluster,
    )
    return _connected_components(edges)


def _chunk_uuids_for(cluster: TopicCluster) -> list[str]:
    """Return the UUIDs of all embeddable items in *cluster*."""
    if cluster.semantic_chunks:
        return [sc.uuid for sc in cluster.semantic_chunks if sc.text.strip()]
    if (cluster.text or "").strip():
        return [cluster.uuid]
    return []


async def _llm_verify_group(
    llm: YandexGPTLLMGateway,
    clusters: list[TopicCluster],
    cluster_sources: dict[str, str],
    model: str,
    pm: PromptManager | None = None,
) -> list[tuple[str, str, list[TopicCluster]]]:
    """Ask the LLM to confirm/refine a candidate megacluster group."""
    prompt = _format_verification_prompt(clusters, cluster_sources, pm=pm)
    logger.info(
        "LLM verifying group of %d clusters: %s",
        len(clusters),
        [c.uuid[:8] for c in clusters],
    )
    try:
        raw, _ = await llm.chat_complete(
            [
                {"role": "system", "content": prompt["system"]},
                {"role": "user", "content": prompt["user"]},
            ],
            model_override=model,
        )
        logger.info("LLM verification response: %s", raw[:500])
        result = _parse_verification_response(raw, clusters)
        logger.info(
            "Parsed %d megacluster groups: %s",
            len(result),
            [(name, desc, len(cs)) for name, desc, cs in result],
        )
        return result
    except Exception:
        logger.exception("LLM verification failed, skipping group")
        return []


def _parse_verification_response(
    raw: str,
    clusters: list[TopicCluster],
) -> list[tuple[str, str, list[TopicCluster]]]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
    data = json.loads(raw)
    mc_list = data.get("megaclusters", [])
    n = len(clusters)
    result: list[tuple[str, str, list[TopicCluster]]] = []
    for entry in mc_list:
        raw_name = str(entry.get("name", ""))
        raw_desc = str(entry.get("description", ""))
        indices = entry.get("cluster_indices", entry.get("indices", []))
        valid = [i for i in indices if isinstance(i, int) and 0 <= i < n]
        if valid:
            grouped_clusters = [clusters[i] for i in valid]
            desc = _derive_megacluster_description(
                raw_desc,
                *(cluster.topic_description for cluster in grouped_clusters),
            )
            name = _derive_megacluster_name(
                raw_name,
                raw_desc,
                *(cluster.topic_description for cluster in grouped_clusters),
            )
            result.append((name, desc, grouped_clusters))
    return result


def _distinct_document_ids(
    clusters: list[TopicCluster],
    cluster_sources: dict[str, str],
) -> list[str]:
    return sorted(
        {
            document_id
            for cluster in clusters
            if (document_id := str(cluster_sources.get(cluster.uuid, "")).strip())
        }
    )


def _cross_document_similarity_score(
    cluster: TopicCluster,
    clusters: list[TopicCluster],
    cluster_sources: dict[str, str],
    centroids: dict[str, list[float]],
) -> tuple[float, int]:
    document_id = str(cluster_sources.get(cluster.uuid, "")).strip()
    centroid = centroids.get(cluster.uuid)
    if not document_id or centroid is None:
        return (0.0, 0)

    similarities: list[float] = []
    for other in clusters:
        if other.uuid == cluster.uuid:
            continue
        other_document_id = str(cluster_sources.get(other.uuid, "")).strip()
        if not other_document_id or other_document_id == document_id:
            continue
        other_centroid = centroids.get(other.uuid)
        if other_centroid is None:
            continue
        similarities.append(_cosine_similarity(centroid, other_centroid))

    if not similarities:
        return (0.0, 0)
    return (sum(similarities) / len(similarities), len(similarities))


def _filter_one_cluster_per_document(
    clusters: list[TopicCluster],
    cluster_sources: dict[str, str],
    centroids: dict[str, list[float]],
) -> list[TopicCluster]:
    """Keep at most one representative cluster per document within a megacluster."""
    clusters_by_document: dict[str, list[TopicCluster]] = defaultdict(list)
    for cluster in clusters:
        document_id = str(cluster_sources.get(cluster.uuid, "")).strip()
        clusters_by_document[document_id].append(cluster)

    selected_cluster_uuids: set[str] = set()
    removed_clusters: list[tuple[str, list[str]]] = []

    for document_id, document_clusters in clusters_by_document.items():
        if len(document_clusters) == 1:
            selected_cluster_uuids.add(document_clusters[0].uuid)
            continue

        best_cluster = document_clusters[0]
        best_key = (
            *_cross_document_similarity_score(
                best_cluster,
                clusters,
                cluster_sources,
                centroids,
            ),
            len(best_cluster.semantic_chunks),
            best_cluster.token_count,
            len(best_cluster.topic_description or ""),
        )

        for candidate in document_clusters[1:]:
            candidate_key = (
                *_cross_document_similarity_score(
                    candidate,
                    clusters,
                    cluster_sources,
                    centroids,
                ),
                len(candidate.semantic_chunks),
                candidate.token_count,
                len(candidate.topic_description or ""),
            )
            if candidate_key > best_key:
                best_cluster = candidate
                best_key = candidate_key

        selected_cluster_uuids.add(best_cluster.uuid)
        removed_clusters.append(
            (
                document_id,
                [
                    cluster.uuid[:8]
                    for cluster in document_clusters
                    if cluster.uuid != best_cluster.uuid
                ],
            )
        )

    filtered_clusters = [
        cluster for cluster in clusters if cluster.uuid in selected_cluster_uuids
    ]
    if removed_clusters:
        logger.info(
            "Filtered duplicate-document clusters from megacluster candidate: kept=%s removed=%s",
            [cluster.uuid[:8] for cluster in filtered_clusters],
            removed_clusters,
        )
    return filtered_clusters


async def identify_megaclusters(
    all_clusters: list[TopicCluster],
    cluster_sources: dict[str, str],
    llm: YandexGPTLLMGateway,
    voyage: VoyageEmbeddingService,
    *,
    prompt_manager: PromptManager | None = None,
    model: str = "YandexGPT",
    centroid_sim_threshold: float = 0.85,
    chunk_sim_threshold: float = 0.85,
    borderline_low: float = 0.80,
    borderline_high: float = 0.90,
    candidate_centroid_floor: float = 0.0,
    top_neighbors_per_cluster: int = 0,
) -> list[MegaCluster]:
    """Embedding-based megaclustering with chunk-to-chunk matching + LLM verification.

    - Single source (≤1 document): each cluster → own megacluster.
    - Multiple sources: centroid similarity + chunk-to-chunk matching + LLM verification,
      then wrap unpaired clusters.
    """
    if not all_clusters:
        return []

    num_sources = len(set(cluster_sources.values()))
    cluster_by_uuid = {c.uuid: c for c in all_clusters}
    covered: set[str] = set()
    megaclusters: list[MegaCluster] = []

    if num_sources >= 2:
        logger.info(
            "Megaclustering %d clusters from %d documents",
            len(all_clusters),
            num_sources,
        )
        chunk_embeddings = await _build_chunk_embeddings(all_clusters, voyage)
        centroids = _compute_cluster_centroids(all_clusters, chunk_embeddings)
        logger.info(
            "Computed %d centroids, %d chunk embeddings",
            len(centroids),
            len(chunk_embeddings),
        )

        if centroids:
            candidate_groups = _find_candidate_groups(
                all_clusters,
                cluster_sources,
                centroids,
                chunk_embeddings,
                centroid_sim_threshold=centroid_sim_threshold,
                chunk_sim_threshold=chunk_sim_threshold,
                borderline_low=borderline_low,
                borderline_high=borderline_high,
                candidate_centroid_floor=candidate_centroid_floor,
                top_neighbors_per_cluster=top_neighbors_per_cluster,
            )
        else:
            logger.warning("No centroids computed — skipping cross-doc grouping")
            candidate_groups = []

        multi_groups = [g for g in candidate_groups if len(g) >= 2]
        logger.info(
            "Found %d candidate groups (%d with 2+ clusters)",
            len(candidate_groups),
            len(multi_groups),
        )

        for group in candidate_groups:
            if len(group) < 2:
                continue
            clusters_in_group = [
                cluster_by_uuid[u] for u in group if u in cluster_by_uuid
            ]
            if len(clusters_in_group) < 2:
                continue

            verified = await _llm_verify_group(
                llm, clusters_in_group, cluster_sources, model, pm=prompt_manager
            )
            for name, desc, sub_clusters in verified:
                if len(sub_clusters) < 2:
                    continue
                filtered_clusters = _filter_one_cluster_per_document(
                    sub_clusters,
                    cluster_sources,
                    centroids,
                )
                if len(filtered_clusters) < 2:
                    continue
                doc_ids = _distinct_document_ids(filtered_clusters, cluster_sources)
                if len(doc_ids) < 2:
                    logger.info(
                        "Skipping same-document megacluster candidate: clusters=%s documents=%s",
                        [cluster.uuid[:8] for cluster in filtered_clusters],
                        doc_ids,
                    )
                    continue
                megaclusters.append(
                    MegaCluster(
                        name=_derive_megacluster_name(
                            name,
                            desc,
                            *(
                                cluster.topic_description
                                for cluster in filtered_clusters
                            ),
                        ),
                        description=desc,
                        clusters=filtered_clusters,
                        document_ids=doc_ids,
                    )
                )
                covered.update(cluster.uuid for cluster in filtered_clusters)

    for c in all_clusters:
        if c.uuid not in covered:
            description = _derive_megacluster_description(c.topic_description)
            megaclusters.append(
                MegaCluster(
                    name=_derive_megacluster_name(c.topic_description, description),
                    description=description,
                    clusters=[c],
                    document_ids=[cluster_sources.get(c.uuid, "")],
                )
            )

    return megaclusters
