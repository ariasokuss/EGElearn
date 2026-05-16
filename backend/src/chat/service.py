"""Chat repository implementation using SQLAlchemy."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import and_, cast, delete as sa_delete, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.chat.entities import Conversation, DocumentInfo, Message, MessageRole
from src.chat.models import Conversation as ConversationModel
from src.chat.models import Message as MessageModel
from src.config import get_settings
from src.files import service as files_service


def _str_uuid(value: uuid.UUID | None) -> str | None:
    return str(value) if value is not None else None


class ChatRepository:
    """Async SQLAlchemy implementation for chat conversations and messages."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create_conversation(
        self,
        user_id: str,
        folder_id: str | None,
        title: str | None,
        *,
        test_session_id: str | None = None,
        question_id: str | None = None,
        lesson_id: str | None = None,
        scope_type: str | None = None,
        feedback_note_id: str | None = None,
    ) -> str:
        async with self._session_factory() as db:
            conv = ConversationModel(
                user_id=user_id,
                folder_id=uuid.UUID(folder_id) if folder_id else None,
                title=title,
                test_session_id=uuid.UUID(test_session_id)
                if test_session_id
                else None,
                question_id=uuid.UUID(question_id) if question_id else None,
                lesson_id=uuid.UUID(lesson_id) if lesson_id else None,
                scope_type=scope_type,
                feedback_note_id=uuid.UUID(feedback_note_id) if feedback_note_id else None,
            )
            db.add(conv)
            await db.commit()
            await db.refresh(conv)
            return str(conv.id)

    async def get_conversation(self, conversation_id: str) -> Conversation | None:
        async with self._session_factory() as db:
            result = await db.execute(
                select(ConversationModel).where(
                    ConversationModel.id == uuid.UUID(conversation_id)
                )
            )
            conv = result.scalar_one_or_none()
            if not conv:
                return None
            return Conversation(
                id=str(conv.id),
                user_id=conv.user_id,
                folder_id=str(conv.folder_id) if conv.folder_id else None,
                title=conv.title,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                test_session_id=_str_uuid(conv.test_session_id),
                question_id=_str_uuid(conv.question_id),
                lesson_id=_str_uuid(conv.lesson_id),
                active_path=[str(uid) for uid in conv.active_path] if conv.active_path else None,
                scope_type=conv.scope_type,
                feedback_note_id=str(conv.feedback_note_id) if conv.feedback_note_id else None,
            )

    async def list_conversations(
        self,
        user_id: str,
        folder_id: str | None,
        *,
        limit: int = 50,
        offset: int = 0,
        test_session_id: str | None = None,
        question_id: str | None = None,
        lesson_id: str | None = None,
        scope_type: str | None = None,
        feedback_note_id: str | None = None,
    ) -> list[dict[str, Any]]:
        preview_len = get_settings().chat.last_message_preview_length

        async with self._session_factory() as db:
            msg_count_subq = (
                select(func.count(MessageModel.id).label("message_count"))
                .where(
                    MessageModel.conversation_id == ConversationModel.id,
                    MessageModel.role.in_(["user", "assistant"]),
                )
                .correlate(ConversationModel)
                .scalar_subquery()
            )

            last_preview_subq = (
                select(func.left(MessageModel.content, preview_len).label("preview"))
                .where(
                    MessageModel.conversation_id == ConversationModel.id,
                    MessageModel.role == "assistant",
                )
                .order_by(MessageModel.created_at.desc())
                .limit(1)
                .correlate(ConversationModel)
                .scalar_subquery()
            )

            if folder_id is None:
                folder_filter = ConversationModel.folder_id.is_(None)
            else:
                folder_filter = ConversationModel.folder_id == uuid.UUID(folder_id)

            if test_session_id is not None and question_id is not None:
                scope_filter = and_(
                    ConversationModel.test_session_id == uuid.UUID(test_session_id),
                    ConversationModel.question_id == uuid.UUID(question_id),
                    ConversationModel.lesson_id.is_(None),
                )
                # Filter by scope_type: treat None as "practice" for backward compat
                if scope_type and scope_type != "practice":
                    scope_filter = and_(
                        scope_filter,
                        ConversationModel.scope_type == scope_type,
                    )
                else:
                    scope_filter = and_(
                        scope_filter,
                        or_(
                            ConversationModel.scope_type.is_(None),
                            ConversationModel.scope_type == "practice",
                        ),
                    )
                if feedback_note_id:
                    scope_filter = and_(
                        scope_filter,
                        ConversationModel.feedback_note_id == uuid.UUID(feedback_note_id),
                    )
            elif lesson_id is not None:
                scope_filter = and_(
                    ConversationModel.test_session_id.is_(None),
                    ConversationModel.question_id.is_(None),
                    ConversationModel.lesson_id == uuid.UUID(lesson_id),
                )
            else:
                scope_filter = and_(
                    ConversationModel.test_session_id.is_(None),
                    ConversationModel.question_id.is_(None),
                    ConversationModel.lesson_id.is_(None),
                )

            result = await db.execute(
                select(
                    ConversationModel.id,
                    ConversationModel.title,
                    ConversationModel.created_at,
                    ConversationModel.updated_at,
                    ConversationModel.test_session_id,
                    ConversationModel.question_id,
                    ConversationModel.lesson_id,
                    ConversationModel.scope_type,
                    ConversationModel.feedback_note_id,
                    func.coalesce(msg_count_subq, 0).label("message_count"),
                    func.coalesce(last_preview_subq, "").label("last_message_preview"),
                )
                .where(
                    ConversationModel.user_id == user_id,
                    folder_filter,
                    scope_filter,
                )
                .order_by(ConversationModel.updated_at.desc())
                .limit(limit)
                .offset(offset)
            )
            rows = result.all()

        return [
            {
                "id": str(row.id),
                "title": row.title,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
                "message_count": row.message_count,
                "last_message_preview": row.last_message_preview or "",
                "test_session_id": _str_uuid(row.test_session_id),
                "question_id": _str_uuid(row.question_id),
                "lesson_id": _str_uuid(row.lesson_id),
                "scope_type": row.scope_type,
                "feedback_note_id": str(row.feedback_note_id) if row.feedback_note_id else None,
            }
            for row in rows
        ]

    async def delete_conversation(self, conversation_id: str) -> bool:
        async with self._session_factory() as db:
            result = await db.execute(
                select(ConversationModel).where(
                    ConversationModel.id == uuid.UUID(conversation_id)
                )
            )
            conv = result.scalar_one_or_none()
            if not conv:
                return False
            await db.delete(conv)
            await db.commit()
            return True

    async def save_message(
        self,
        message: Message,
        *,
        parent_id: str | None = None,
        version_index: int = 1,
    ) -> str:
        async with self._session_factory() as db:
            msg = MessageModel(
                id=uuid.UUID(message.id),
                conversation_id=uuid.UUID(message.conversation_id),
                role=message.role.value,
                content=message.content,
                metadata_=message.metadata or {},
                parent_id=uuid.UUID(parent_id) if parent_id else None,
                version_index=version_index,
            )
            db.add(msg)
            await db.commit()
            return message.id

    async def get_messages(
        self,
        conversation_id: str,
        roles: list[MessageRole] | None = None,
        limit: int | None = None,
    ) -> list[Message]:
        async with self._session_factory() as db:
            q = (
                select(MessageModel)
                .where(MessageModel.conversation_id == uuid.UUID(conversation_id))
                .order_by(MessageModel.created_at.asc())
            )
            if roles:
                q = q.where(MessageModel.role.in_([r.value for r in roles]))
            if limit is not None:
                q = q.limit(limit)

            result = await db.execute(q)
            rows = result.scalars().all()

        return [self._row_to_message(r) for r in rows]

    async def get_messages_page(
        self,
        conversation_id: str,
        roles: list[MessageRole],
        cursor: str | None,
        limit: int,
    ) -> tuple[list[Message], bool, str | None]:
        role_values = [r.value for r in roles]
        conv_uuid = uuid.UUID(conversation_id)

        async with self._session_factory() as db:
            cursor_timestamp = None
            if cursor:
                cursor_result = await db.execute(
                    select(MessageModel.created_at).where(
                        MessageModel.id == uuid.UUID(cursor),
                        MessageModel.conversation_id == conv_uuid,
                    )
                )
                cursor_row = cursor_result.scalar_one_or_none()
                if cursor_row is not None:
                    cursor_timestamp = cursor_row

            q = (
                select(MessageModel)
                .where(
                    MessageModel.conversation_id == conv_uuid,
                    MessageModel.role.in_(role_values),
                )
                .order_by(MessageModel.created_at.desc())
                .limit(limit + 1)
            )
            if cursor_timestamp is not None:
                q = q.where(MessageModel.created_at < cursor_timestamp)

            result = await db.execute(q)
            rows = list(result.scalars().all())

        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]

        next_cursor = str(rows[-1].id) if has_more and rows else None
        rows = list(reversed(rows))
        messages = [self._row_to_message(r) for r in rows]
        return messages, has_more, next_cursor

    async def update_conversation_title(self, conversation_id: str, title: str) -> None:
        async with self._session_factory() as db:
            result = await db.execute(
                select(ConversationModel).where(
                    ConversationModel.id == uuid.UUID(conversation_id)
                )
            )
            conv = result.scalar_one_or_none()
            if conv:
                conv.title = title
                await db.commit()

    async def touch_conversation(self, conversation_id: str) -> None:
        async with self._session_factory() as db:
            await db.execute(
                update(ConversationModel)
                .where(ConversationModel.id == uuid.UUID(conversation_id))
                .values(updated_at=func.now())
            )
            await db.commit()

    async def get_message(
        self, message_id: str, conversation_id: str
    ) -> Message | None:
        async with self._session_factory() as db:
            result = await db.execute(
                select(MessageModel).where(
                    MessageModel.id == uuid.UUID(message_id),
                    MessageModel.conversation_id == uuid.UUID(conversation_id),
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return self._row_to_message(row)

    async def delete_messages_from(self, conversation_id: str, message_id: str) -> int:
        """Delete the given message and every message created at or after it in the conversation."""
        async with self._session_factory() as db:
            ts_result = await db.execute(
                select(MessageModel.created_at).where(
                    MessageModel.id == uuid.UUID(message_id),
                    MessageModel.conversation_id == uuid.UUID(conversation_id),
                )
            )
            target_ts = ts_result.scalar_one_or_none()
            if target_ts is None:
                return 0
            result = await db.execute(
                sa_delete(MessageModel).where(
                    MessageModel.conversation_id == uuid.UUID(conversation_id),
                    MessageModel.created_at >= target_ts,
                )
            )
            await db.commit()
            return result.rowcount

    async def get_folder_documents(
        self, user_id: str, folder_id: str | None
    ) -> list[DocumentInfo]:
        if folder_id is None:
            return []

        user_uuid = uuid.UUID(user_id)
        folder_uuid = uuid.UUID(folder_id)

        async with self._session_factory() as db:
            docs = await files_service.list_documents(db, user_uuid, folder_uuid)

        return [
            DocumentInfo(
                document_id=str(d.id),
                name=d.name,
                page_count=d.page_count or 1,
            )
            for d in docs
        ]

    async def get_active_path_messages(
        self,
        conversation_id: str,
        roles: list[MessageRole],
        cursor: str | None,
        limit: int,
    ) -> tuple[list[Message], bool, str | None]:
        """Fetch messages on the active path with cursor-based pagination.

        Falls back to get_messages_page when active_path is NULL.
        """
        conv_uuid = uuid.UUID(conversation_id)

        async with self._session_factory() as db:
            # Fetch active_path from conversation
            result = await db.execute(
                select(ConversationModel.active_path).where(
                    ConversationModel.id == conv_uuid
                )
            )
            active_path = result.scalar_one_or_none()

        if not active_path:
            return await self.get_messages_page(conversation_id, roles, cursor, limit)

        role_values = [r.value for r in roles]
        path_uuids = list(active_path)

        async with self._session_factory() as db:
            # Determine cursor position in the active_path
            cursor_pos: int | None = None
            if cursor:
                cursor_uuid = uuid.UUID(cursor)
                try:
                    cursor_pos = path_uuids.index(cursor_uuid)
                except ValueError:
                    cursor_pos = None

            # Build query: messages WHERE id IN (active_path) filtered by role,
            # ordered by position in the active_path array (descending for pagination).
            # We use array_position to order by position in the path.
            pos_expr = func.array_position(
                active_path, MessageModel.id
            )

            q = (
                select(MessageModel)
                .where(
                    MessageModel.conversation_id == conv_uuid,
                    MessageModel.id.in_(path_uuids),
                    MessageModel.role.in_(role_values),
                )
                .order_by(pos_expr.desc())
                .limit(limit + 1)
            )

            if cursor_pos is not None:
                # Only fetch messages with position < cursor_pos (earlier in path)
                q = q.where(pos_expr < cursor_pos + 1)  # array_position is 1-based

            result = await db.execute(q)
            rows = list(result.scalars().all())

        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]

        next_cursor = str(rows[-1].id) if has_more and rows else None
        rows = list(reversed(rows))
        messages = [self._row_to_message(r) for r in rows]
        return messages, has_more, next_cursor

    async def get_active_path_history(
        self,
        conversation_id: str,
        roles: list[MessageRole],
    ) -> list[Message]:
        """Return all messages on the active path (single query, no pagination).

        Falls back to ``get_messages`` when active_path is NULL.
        """
        conv_uuid = uuid.UUID(conversation_id)
        role_values = [r.value for r in roles]

        async with self._session_factory() as db:
            # Single query: fetch active_path from conversation and join with
            # messages in one round-trip.
            conv_path = (
                select(ConversationModel.active_path)
                .where(ConversationModel.id == conv_uuid)
                .scalar_subquery()
            )

            pos_expr = func.array_position(conv_path, MessageModel.id)

            q = (
                select(MessageModel)
                .where(
                    MessageModel.conversation_id == conv_uuid,
                    MessageModel.role.in_(role_values),
                    # Only rows whose id appears in the active_path array
                    pos_expr.is_not(None),
                )
                .order_by(pos_expr.asc())
            )
            result = await db.execute(q)
            rows = result.scalars().all()

        if not rows:
            # active_path was NULL or empty — fall back to all messages
            return await self.get_messages(conversation_id, roles)

        return [self._row_to_message(r) for r in rows]

    async def get_sibling_count(
        self, message_id: str, conversation_id: str
    ) -> int:
        """Count sibling messages (same parent_id). For root messages, count
        other root messages of the same role in the conversation."""
        msg_uuid = uuid.UUID(message_id)
        conv_uuid = uuid.UUID(conversation_id)

        async with self._session_factory() as db:
            # Get the target message's parent_id and role
            result = await db.execute(
                select(MessageModel.parent_id, MessageModel.role).where(
                    MessageModel.id == msg_uuid,
                    MessageModel.conversation_id == conv_uuid,
                )
            )
            row = result.one_or_none()
            if row is None:
                return 0

            parent_id, role = row

            if parent_id is not None:
                # Count messages with same parent_id AND same role
                result = await db.execute(
                    select(func.count(MessageModel.id)).where(
                        MessageModel.conversation_id == conv_uuid,
                        MessageModel.parent_id == parent_id,
                        MessageModel.role == role,
                    )
                )
            else:
                # Root messages: count other root messages of same role
                result = await db.execute(
                    select(func.count(MessageModel.id)).where(
                        MessageModel.conversation_id == conv_uuid,
                        MessageModel.parent_id.is_(None),
                        MessageModel.role == role,
                    )
                )

            return result.scalar_one()

    async def get_siblings(
        self, message_id: str, conversation_id: str
    ) -> list[Message]:
        """Return all sibling messages ordered by version_index (single query)."""
        msg_uuid = uuid.UUID(message_id)
        conv_uuid = uuid.UUID(conversation_id)

        # Subquery: get parent_id and role of the target message
        target = (
            select(MessageModel.parent_id, MessageModel.role)
            .where(
                MessageModel.id == msg_uuid,
                MessageModel.conversation_id == conv_uuid,
            )
            .subquery()
        )

        # Main query: fetch siblings sharing the same parent_id and role.
        # Handles NULL parent_id via coalesce trick — compare on a sentinel
        # that never matches a real UUID.
        q = (
            select(MessageModel)
            .where(
                MessageModel.conversation_id == conv_uuid,
                MessageModel.role == target.c.role,
                or_(
                    and_(target.c.parent_id.is_not(None), MessageModel.parent_id == target.c.parent_id),
                    and_(target.c.parent_id.is_(None), MessageModel.parent_id.is_(None)),
                ),
            )
            .order_by(MessageModel.version_index.asc())
        )

        async with self._session_factory() as db:
            result = await db.execute(q)
            rows = result.scalars().all()

        return [self._row_to_message(r) for r in rows]

    async def get_next_version_index(
        self, parent_id: str | None, conversation_id: str, role: str | None = None
    ) -> int:
        """Return MAX(version_index) + 1 for messages with the given parent_id.

        When *role* is provided the max is scoped to that role only, preventing
        tool_call / tool_result rows from inflating the sequence for user or
        assistant messages.
        """
        conv_uuid = uuid.UUID(conversation_id)

        async with self._session_factory() as db:
            filters = [MessageModel.conversation_id == conv_uuid]
            if parent_id is not None:
                filters.append(MessageModel.parent_id == uuid.UUID(parent_id))
            else:
                filters.append(MessageModel.parent_id.is_(None))
            if role is not None:
                filters.append(MessageModel.role == role)

            result = await db.execute(
                select(func.coalesce(func.max(MessageModel.version_index), 0)).where(*filters)
            )

            max_idx = result.scalar_one()
            return max_idx + 1

    async def get_sibling_counts_batch(
        self, message_ids: list[str], conversation_id: str
    ) -> dict[str, int]:
        """Return {message_id: sibling_count} for a batch of messages in one query."""
        info = await self.get_sibling_info_batch(message_ids, conversation_id)
        return {mid: v[0] for mid, v in info.items()}

    async def get_sibling_info_batch(
        self, message_ids: list[str], conversation_id: str
    ) -> dict[str, tuple[int, int]]:
        """Return {message_id: (sibling_count, sibling_position)} for a batch.

        ``sibling_position`` is the 1-based rank of the message among its
        same-role siblings ordered by version_index.  This is what the frontend
        should display instead of the raw ``version_index`` value, because
        version_index can have gaps when tool messages shared the same parent.

        Uses window functions to compute everything in a single query instead
        of N per-message round-trips.
        """
        if not message_ids:
            return {}
        conv_uuid = uuid.UUID(conversation_id)
        msg_uuids = [uuid.UUID(mid) for mid in message_ids]

        # Use COALESCE(parent_id, id) as the partition key so that
        # NULL parent_id rows each form their own group correctly.
        # We need a sentinel for NULL parent_id to allow proper partitioning.
        sentinel = uuid.UUID("00000000-0000-0000-0000-000000000000")

        partition_key = func.coalesce(MessageModel.parent_id, sentinel)

        # Step 1: find which (parent_id, role) groups the requested messages
        # belong to.
        targets = (
            select(
                func.coalesce(MessageModel.parent_id, sentinel).label("grp_parent"),
                MessageModel.role.label("grp_role"),
            )
            .where(
                MessageModel.id.in_(msg_uuids),
                MessageModel.conversation_id == conv_uuid,
            )
            .distinct()
            .subquery("targets")
        )

        # Step 2: for all messages in those groups, compute row_number and count
        # via window functions in a single pass.
        window = {
            "partition_by": [partition_key, MessageModel.role],
            "order_by": MessageModel.version_index.asc(),
        }

        ranked = (
            select(
                MessageModel.id,
                func.row_number().over(**window).label("pos"),
                func.count().over(
                    partition_by=[partition_key, MessageModel.role]
                ).label("cnt"),
            )
            .join(
                targets,
                and_(
                    partition_key == targets.c.grp_parent,
                    MessageModel.role == targets.c.grp_role,
                ),
            )
            .where(
                MessageModel.conversation_id == conv_uuid,
                MessageModel.role.in_(["user", "assistant"]),
            )
            .subquery("ranked")
        )

        # Step 3: filter to only the requested message IDs.
        stmt = select(ranked.c.id, ranked.c.cnt, ranked.c.pos).where(
            ranked.c.id.in_(msg_uuids)
        )

        async with self._session_factory() as db:
            result = await db.execute(stmt)
            info: dict[str, tuple[int, int]] = {}
            for row in result.all():
                info[str(row[0])] = (row[1], max(row[2], 1))

        return info

    async def get_messages_batch(
        self, message_ids: list[str], conversation_id: str
    ) -> dict[str, Message]:
        """Fetch multiple messages by ID in a single query. Returns {id: Message}."""
        if not message_ids:
            return {}
        conv_uuid = uuid.UUID(conversation_id)
        msg_uuids = [uuid.UUID(mid) for mid in message_ids]

        async with self._session_factory() as db:
            result = await db.execute(
                select(MessageModel).where(
                    MessageModel.id.in_(msg_uuids),
                    MessageModel.conversation_id == conv_uuid,
                )
            )
            rows = result.scalars().all()

        return {str(r.id): self._row_to_message(r) for r in rows}

    async def get_subtree_path(
        self, message_id: str, conversation_id: str, active_path: list[str]
    ) -> list[str]:
        """Walk from a message to the leaf, building the path.

        At each level, prefer a child that was in active_path; fallback to
        highest version_index.  Uses a single recursive CTE instead of N
        round-trips.
        """
        conv_uuid = uuid.UUID(conversation_id)
        msg_uuid = uuid.UUID(message_id)
        active_uuids = [uuid.UUID(mid) for mid in active_path] if active_path else []

        from sqlalchemy import bindparam
        from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY, UUID as PG_UUID

        raw = text("""
            WITH RECURSIVE walk AS (
                SELECT :start_id ::uuid AS node_id, 0 AS depth
              UNION ALL
                SELECT child.id, w.depth + 1
                FROM walk w
                JOIN LATERAL (
                    SELECT m.id
                    FROM messages m
                    WHERE m.parent_id = w.node_id
                      AND m.conversation_id = :conv_id
                    ORDER BY
                        (m.id = ANY(:active_arr)) DESC,
                        m.version_index DESC
                    LIMIT 1
                ) child ON true
            )
            SELECT node_id FROM walk ORDER BY depth
        """).bindparams(
            bindparam("active_arr", type_=PG_ARRAY(PG_UUID(as_uuid=True))),
        )

        async with self._session_factory() as db:
            result = await db.execute(
                raw,
                {"start_id": msg_uuid, "conv_id": conv_uuid, "active_arr": active_uuids},
            )
            rows = result.all()

        return [str(r[0]) for r in rows]

    async def update_active_path(
        self, conversation_id: str, new_path: list[str]
    ) -> None:
        """Atomic update of the active_path array on conversation."""
        conv_uuid = uuid.UUID(conversation_id)
        path_uuids = [uuid.UUID(mid) for mid in new_path]

        async with self._session_factory() as db:
            await db.execute(
                update(ConversationModel)
                .where(ConversationModel.id == conv_uuid)
                .values(active_path=path_uuids)
            )
            await db.commit()

    async def append_to_active_path(
        self, conversation_id: str, message_id: str
    ) -> None:
        """Atomically append a message ID to active_path using array_append."""
        conv_uuid = uuid.UUID(conversation_id)
        msg_uuid = uuid.UUID(message_id)

        async with self._session_factory() as db:
            await db.execute(
                update(ConversationModel)
                .where(ConversationModel.id == conv_uuid)
                .values(
                    active_path=func.coalesce(
                        func.array_append(ConversationModel.active_path, msg_uuid),
                        cast(func.array_append(
                            cast(None, ARRAY(UUID(as_uuid=True))),
                            msg_uuid,
                        ), ARRAY(UUID(as_uuid=True))),
                    )
                )
            )
            await db.commit()

    async def get_active_path(self, conversation_id: str) -> list[str]:
        """Return the active_path as list[str]."""
        conv_uuid = uuid.UUID(conversation_id)

        async with self._session_factory() as db:
            result = await db.execute(
                select(ConversationModel.active_path).where(
                    ConversationModel.id == conv_uuid
                )
            )
            path = result.scalar_one_or_none()

        if not path:
            return []
        return [str(uid) for uid in path]

    @staticmethod
    def _row_to_message(row: MessageModel) -> Message:
        return Message(
            id=str(row.id),
            conversation_id=str(row.conversation_id),
            role=MessageRole(row.role),
            content=row.content,
            metadata=row.metadata_ or {},
            created_at=row.created_at,
            parent_id=str(row.parent_id) if row.parent_id else None,
            version_index=row.version_index,
        )
