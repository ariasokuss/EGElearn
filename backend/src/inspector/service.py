import uuid
from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.qdrant import ChunkRecord, ClusterRecord, QdrantStore
from src.core.s3 import S3Client
from src.files.models import Document
from src.inspector import repository
from src.inspector.schemas import (
    ChunkRead,
    ClusterRead,
    ClusterBundleRead,
    DocumentInspectorRead,
    DocumentLiveStatusRead,
    DocumentRead,
    DocumentSummaryRead,
    FolderRead,
    FolderSummaryRead,
    InspectorOverviewRead,
    JobSummaryRead,
    MegaclusterSummaryRead,
    QdrantObjectRead,
    QdrantSnapshotRead,
    StorageSnapshotRead,
)
from src.processing.markdown import infer_page_count
from src.processing.models import MegaClusterRecord, ProcessingJob

MAX_ATTEMPTS = 3


def _document_to_read(document: Document) -> DocumentRead:
    job = document.processing_job
    status = job.status.value if job else "unknown"
    error = job.error_message if job else None
    page_count = document.page_count
    if page_count is None:
        page_count = infer_page_count(
            document.markdown_content,
            content_type=document.content_type,
        )
    return DocumentRead(
        id=document.id,
        folder_id=document.folder_id,
        user_id=document.user_id,
        name=document.name,
        original_filename=document.original_filename,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        page_count=page_count,
        source_s3_key=document.source_s3_key,
        processed_s3_key=document.processed_s3_key,
        processing_status=status,
        error_message=error,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def _backfill_document_page_counts(documents: Iterable[Document]) -> bool:
    changed = False
    for document in documents:
        if document.page_count is not None:
            continue
        inferred = infer_page_count(
            document.markdown_content,
            content_type=document.content_type,
        )
        if inferred is None:
            continue
        document.page_count = inferred
        changed = True
    return changed


def _chunk_record_to_read(record: ChunkRecord) -> ChunkRead:
    return ChunkRead(
        chunk_id=record.chunk_id,
        cluster_id=record.cluster_id,
        page=record.page,
        text=record.content,
    )


def _cluster_record_to_read(record: ClusterRecord) -> ClusterRead:
    return ClusterRead(
        cluster_id=record.cluster_id,
        topic_description=record.description,
        content_text=record.content,
        cluster_type=record.content_type,
        content_quality=record.content_quality,
        document_pages=record.pages,
        chunk_ids=None,
    )


def _chunk_record_to_qdrant_object(record: ChunkRecord) -> QdrantObjectRead:
    payload = record.model_dump(exclude={"chunk_id"})
    payload["chunk_id"] = str(record.chunk_id)
    return QdrantObjectRead(
        object_id=str(record.chunk_id),
        properties=payload,
    )


def _cluster_record_to_qdrant_object(record: ClusterRecord) -> QdrantObjectRead:
    payload = record.model_dump(exclude={"cluster_id"})
    payload["cluster_id"] = str(record.cluster_id)
    return QdrantObjectRead(
        object_id=str(record.cluster_id),
        properties=payload,
    )


def _megacluster_record_to_read(
    record: MegaClusterRecord,
    *,
    qdrant_clusters: list[QdrantObjectRead] | None = None,
) -> MegaclusterSummaryRead:
    cluster_ids = [str(cluster_id) for cluster_id in (record.cluster_uuids or [])]
    document_ids = [str(document_id) for document_id in (record.document_ids or [])]
    name = (
        (record.name or "").strip()
        or (record.description or "").strip()
        or "Untitled topic"
    )
    description = (record.description or "").strip() or name
    qdrant_clusters = qdrant_clusters or []
    cluster_topics = [
        str(cluster.properties.get("description", "")).strip()
        for cluster in qdrant_clusters
        if str(cluster.properties.get("description", "")).strip()
    ]
    return MegaclusterSummaryRead(
        id=record.id,
        name=name,
        description=description,
        document_ids=document_ids,
        cluster_ids=cluster_ids,
        cluster_count=len(cluster_ids),
        progress=100,
        created_at=record.created_at,
        cluster_topics=cluster_topics,
        qdrant_clusters=qdrant_clusters,
    )


def _should_expose_megacluster(record: MegaClusterRecord) -> bool:
    distinct_documents = {
        str(document_id).strip()
        for document_id in (record.document_ids or [])
        if str(document_id).strip()
    }
    cluster_count = len(record.cluster_uuids or [])
    return len(distinct_documents) >= 2 or cluster_count <= 1


class InspectorService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        s3: S3Client,
        qdrant: QdrantStore,
    ) -> None:
        self._session_factory = session_factory
        self._s3 = s3
        self._qdrant = qdrant

    async def _count_qdrant(
        self,
        user_id: str,
        *,
        document_id: str,
        folder_id: str | None = None,
    ) -> tuple[int, int]:
        """Return (cluster_count, chunk_count) for a document."""
        clusters, _ = await self._qdrant.get_clusters(
            user_id=user_id,
            document_id=document_id,
            folder_id=folder_id,
            limit=10_000,
        )
        chunks, _ = await self._qdrant.get_chunks(
            user_id=user_id,
            document_id=document_id,
            folder_id=folder_id,
            limit=10_000,
        )
        return len(clusters), len(chunks)

    async def get_overview(self, user_id: uuid.UUID) -> InspectorOverviewRead | None:
        async with self._session_factory() as session:
            user = await repository.get_user(session, user_id)
            if user is None:
                return None

            folders = await repository.list_folders(session, user_id)
            recent_jobs = await repository.list_recent_jobs(session, limit=250)
            user_id_str = str(user_id)
            folder_reads: list[FolderSummaryRead] = []

            for folder in folders:
                documents = await repository.list_documents(
                    session, folder_id=folder.id, user_id=user_id
                )
                if _backfill_document_page_counts(documents):
                    await session.commit()
                megaclusters = await repository.list_megaclusters(
                    session,
                    folder_id=folder.id,
                    user_id=user_id,
                )
                folder_qdrant_clusters, _ = await self._qdrant.get_clusters(
                    user_id=user_id_str,
                    folder_id=str(folder.id),
                    limit=10_000,
                )
                document_reads: list[DocumentSummaryRead] = []
                cluster_count = 0
                chunk_count = 0
                qdrant_clusters_by_megacluster: dict[str, list[QdrantObjectRead]] = {}
                for cluster_record in folder_qdrant_clusters:
                    megacluster_id = str(cluster_record.megacluster_id or "").strip()
                    if not megacluster_id:
                        continue
                    qdrant_clusters_by_megacluster.setdefault(
                        megacluster_id, []
                    ).append(_cluster_record_to_qdrant_object(cluster_record))
                megacluster_reads = [
                    _megacluster_record_to_read(
                        megacluster,
                        qdrant_clusters=qdrant_clusters_by_megacluster.get(
                            str(megacluster.id), []
                        ),
                    )
                    for megacluster in megaclusters
                    if _should_expose_megacluster(megacluster)
                ]

                for document in documents:
                    doc_cluster_count, doc_chunk_count = await self._count_qdrant(
                        user_id_str,
                        document_id=str(document.id),
                        folder_id=str(folder.id),
                    )
                    cluster_count += doc_cluster_count
                    chunk_count += doc_chunk_count

                    doc_read = _document_to_read(document)
                    document_reads.append(
                        DocumentSummaryRead(
                            **doc_read.model_dump(),
                            cluster_count=doc_cluster_count,
                            chunk_count=doc_chunk_count,
                            recent_jobs=self._serialize_jobs(
                                self._matching_jobs(
                                    recent_jobs,
                                    folder_id=folder.id,
                                    document_id=document.id,
                                ),
                                limit=4,
                            ),
                        )
                    )

                folder_reads.append(
                    FolderSummaryRead(
                        **FolderRead.model_validate(folder).model_dump(),
                        document_count=len(document_reads),
                        cluster_count=cluster_count,
                        chunk_count=chunk_count,
                        megacluster_count=len(megacluster_reads),
                        documents=document_reads,
                        megaclusters=megacluster_reads,
                        recent_jobs=self._serialize_jobs(
                            self._matching_jobs(recent_jobs, folder_id=folder.id),
                            limit=8,
                        ),
                    )
                )

            return InspectorOverviewRead(
                user_id=user.id,
                email=user.email,
                folders=folder_reads,
            )

    async def get_folder_status(
        self, user_id: uuid.UUID, folder_id: uuid.UUID
    ) -> FolderSummaryRead | None:
        overview = await self.get_overview(user_id)
        if overview is None:
            return None
        for folder in overview.folders:
            if folder.id == folder_id:
                return folder
        return None

    async def get_document_detail(
        self,
        *,
        user_id: uuid.UUID,
        folder_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> DocumentInspectorRead | None:
        async with self._session_factory() as session:
            folder = await repository.get_folder(session, folder_id, user_id)
            if folder is None:
                return None

            document = await repository.get_document(
                session,
                folder_id=folder_id,
                document_id=document_id,
                user_id=user_id,
            )
            if document is None:
                return None
            if _backfill_document_page_counts([document]):
                await session.commit()

            folder_megaclusters = await repository.list_megaclusters(
                session,
                folder_id=folder_id,
                user_id=user_id,
            )
            markdown: str | None = None
            if document.processed_s3_key:
                try:
                    markdown_bytes = await self._s3.download_bytes(
                        document.processed_s3_key
                    )
                    markdown = markdown_bytes.decode("utf-8", errors="replace")
                except Exception:
                    pass

            recent_jobs = await repository.list_recent_jobs(session, limit=250)
            document_jobs = self._serialize_jobs(
                self._matching_jobs(
                    recent_jobs,
                    folder_id=folder_id,
                    document_id=document_id,
                ),
                limit=8,
            )

        user_id_str = str(user_id)
        folder_id_str = str(folder_id)
        document_id_str = str(document_id)

        clusters, _ = await self._qdrant.get_clusters(
            user_id=user_id_str,
            folder_id=folder_id_str,
            document_id=document_id_str,
            limit=500,
        )
        chunks, _ = await self._qdrant.get_chunks(
            user_id=user_id_str,
            folder_id=folder_id_str,
            document_id=document_id_str,
            limit=500,
        )
        folder_clusters, _ = await self._qdrant.get_clusters(
            user_id=user_id_str,
            folder_id=folder_id_str,
            limit=10_000,
        )

        clusters_by_id: dict[str, ClusterRead] = {}
        for rec in clusters:
            cr = _cluster_record_to_read(rec)
            clusters_by_id[str(cr.cluster_id)] = cr

        chunks_by_cluster: dict[str, list[ChunkRead]] = {}
        for rec in chunks:
            cr = _chunk_record_to_read(rec)
            chunks_by_cluster.setdefault(rec.cluster_id, []).append(cr)

        cluster_bundles: list[ClusterBundleRead] = [
            ClusterBundleRead(
                cluster=cluster,
                chunks=chunks_by_cluster.get(str(cluster.cluster_id), []),
            )
            for cluster in clusters_by_id.values()
        ]

        qdrant_objects_clusters = [
            _cluster_record_to_qdrant_object(r) for r in clusters
        ]
        qdrant_objects_chunks = [_chunk_record_to_qdrant_object(r) for r in chunks]
        qdrant_clusters_by_megacluster: dict[str, list[QdrantObjectRead]] = {}
        for cluster_record in folder_clusters:
            megacluster_id = str(cluster_record.megacluster_id or "").strip()
            if not megacluster_id:
                continue
            qdrant_clusters_by_megacluster.setdefault(megacluster_id, []).append(
                _cluster_record_to_qdrant_object(cluster_record)
            )
        megacluster_reads = [
            _megacluster_record_to_read(
                megacluster,
                qdrant_clusters=qdrant_clusters_by_megacluster.get(
                    str(megacluster.id), []
                ),
            )
            for megacluster in folder_megaclusters
            if _should_expose_megacluster(megacluster)
            if document_id_str
            in {str(doc_id) for doc_id in (megacluster.document_ids or [])}
        ]

        counts = {
            "clusters": len(clusters),
            "chunks": len(chunks),
            "megaclusters": len(megacluster_reads),
        }
        notes = [
            f"Clusters in Qdrant for this document: {counts['clusters']}.",
            f"Chunks in Qdrant for this document: {counts['chunks']}.",
            f"Megaclusters in PostgreSQL referencing this document: {counts['megaclusters']}.",
        ]

        qdrant_snapshot = QdrantSnapshotRead(
            clusters=qdrant_objects_clusters,
            chunks=qdrant_objects_chunks,
        )
        return DocumentInspectorRead(
            folder=FolderRead.model_validate(folder),
            document=_document_to_read(document),
            markdown=markdown,
            clusters=cluster_bundles,
            megaclusters=megacluster_reads,
            recent_jobs=document_jobs,
            qdrant=qdrant_snapshot,
            weaviate=qdrant_snapshot,
            storage=StorageSnapshotRead(
                qdrant_counts=counts,
                weaviate_counts=counts,
                database_counts=counts,
                notes=notes,
            ),
        )

    async def get_document_live_status(
        self,
        *,
        user_id: uuid.UUID,
        folder_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> DocumentLiveStatusRead | None:
        async with self._session_factory() as session:
            folder = await repository.get_folder(session, folder_id, user_id)
            if folder is None:
                return None

            document = await repository.get_document(
                session,
                folder_id=folder_id,
                document_id=document_id,
                user_id=user_id,
            )
            if document is None:
                return None

            recent_jobs = await repository.list_recent_jobs(session, limit=250)
            document_jobs = self._serialize_jobs(
                self._matching_jobs(
                    recent_jobs,
                    folder_id=folder_id,
                    document_id=document_id,
                ),
                limit=8,
            )

        cluster_count, chunk_count = await self._count_qdrant(
            str(user_id),
            document_id=str(document_id),
            folder_id=str(folder_id),
        )

        return DocumentLiveStatusRead(
            document=_document_to_read(document),
            recent_jobs=document_jobs,
            cluster_count=cluster_count,
            chunk_count=chunk_count,
        )

    def _matching_jobs(
        self,
        jobs: Iterable[ProcessingJob],
        *,
        folder_id: uuid.UUID,
        document_id: uuid.UUID | None = None,
    ) -> list[ProcessingJob]:
        matched: list[ProcessingJob] = []
        for job in jobs:
            if job.folder_id != folder_id:
                continue
            if document_id is not None and job.document_id != document_id:
                continue
            matched.append(job)
        return matched

    def _serialize_jobs(
        self, jobs: Iterable[ProcessingJob], *, limit: int
    ) -> list[JobSummaryRead]:
        result: list[JobSummaryRead] = []
        for job in list(jobs)[:limit]:
            result.append(
                JobSummaryRead(
                    id=job.id,
                    kind="processing",
                    status=job.status.value,
                    attempts=job.attempt_count,
                    max_attempts=MAX_ATTEMPTS,
                    error=job.error_message,
                    payload={
                        "document_id": str(job.document_id),
                        "folder_id": str(job.folder_id),
                    },
                    created_at=job.created_at,
                    updated_at=job.updated_at,
                )
            )
        return result
