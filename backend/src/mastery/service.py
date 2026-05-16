"""Mastery engine — Beta-Bayesian computation with per-event temporal decay."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.mastery.models import EvidenceEvent

# ─── Engine Parameters (defaults, overridden by config) ───────────────


def _cfg():
    return get_settings().mastery


QUALITY_WEIGHTS: dict[str, float] = {
    "inline_mcq": 0.5,
    "inline_short": 0.7,
    "mini_feynman": 0.7,
    "feynman": 1.0,
    "lesson_test": 1.0,
    "standalone_test": 1.2,
    "past_paper": 1.5,
    "verify_card": 1.0,
}


# ─── Pure computation (no DB) ─────────────────────────────────────────


def _beta_ppf(p: float, a: float, b: float) -> float:
    """Inverse CDF (quantile) of Beta distribution.

    Uses scipy if available, otherwise falls back to a Newton's method
    approximation using the regularized incomplete beta function.
    """
    try:
        from scipy.stats import beta as beta_dist

        return float(beta_dist.ppf(p, a, b))
    except ImportError:
        pass
    # Pure-Python fallback using math.lgamma for the Beta regularized function
    return _beta_ppf_pure(p, a, b)


def _beta_ppf_pure(
    p: float, a: float, b: float, tol: float = 1e-8, max_iter: int = 200
) -> float:
    """Pure-Python Beta PPF via bisection on the regularized incomplete beta function."""
    import math

    def _log_beta(a: float, b: float) -> float:
        return math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)

    def _betainc(x: float, a: float, b: float) -> float:
        """Regularized incomplete beta function via continued fraction (Lentz)."""
        if x <= 0:
            return 0.0
        if x >= 1:
            return 1.0
        # Use symmetry relation for better convergence
        if x > (a + 1) / (a + b + 2):
            return 1.0 - _betainc(1 - x, b, a)

        log_prefix = (
            a * math.log(x) + b * math.log(1 - x) - _log_beta(a, b) - math.log(a)
        )
        prefix = math.exp(log_prefix)

        # Continued fraction (Lentz's method)
        c = 1.0
        d = 1.0 - (a + b) * x / (a + 1)
        if abs(d) < 1e-30:
            d = 1e-30
        d = 1.0 / d
        result = d

        for m in range(1, max_iter + 1):
            # Even step
            num = m * (b - m) * x / ((a + 2 * m - 1) * (a + 2 * m))
            d = 1.0 + num * d
            if abs(d) < 1e-30:
                d = 1e-30
            c = 1.0 + num / c
            if abs(c) < 1e-30:
                c = 1e-30
            d = 1.0 / d
            result *= d * c

            # Odd step
            num = -(a + m) * (a + b + m) * x / ((a + 2 * m) * (a + 2 * m + 1))
            d = 1.0 + num * d
            if abs(d) < 1e-30:
                d = 1e-30
            c = 1.0 + num / c
            if abs(c) < 1e-30:
                c = 1e-30
            d = 1.0 / d
            delta = d * c
            result *= delta

            if abs(delta - 1.0) < tol:
                break

        return prefix * result

    # Bisection to invert CDF
    lo, hi = 0.0, 1.0
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        if _betainc(mid, a, b) < p:
            lo = mid
        else:
            hi = mid
        if (hi - lo) < tol:
            break
    return (lo + hi) / 2


def compute_mastery_from_events(
    events: list[EvidenceEvent],
    now: datetime | None = None,
) -> dict:
    """Replay the event ledger and compute mastery.

    Returns dict with alpha, beta, mastery (0-100), active_events count.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    cfg = _cfg()
    alpha = cfg.alpha_prior
    beta_param = cfg.beta_prior
    active = 0

    for ev in events:
        if ev.invalidated:
            continue
        days_ago = (now - ev.timestamp).total_seconds() / 86400
        if days_ago < 0:
            days_ago = 0
        decay = cfg.lambda_decay**days_ago

        # Correct: discounted on repeat; wrong: always full weight
        alpha += ev.quality_weight * ev.score * ev.repeat_discount * decay
        beta_param += ev.quality_weight * (1 - ev.score) * decay
        active += 1

    mastery = _beta_ppf(cfg.mastery_percentile, alpha, beta_param) * 100
    effective_sample = (alpha + beta_param) - (cfg.alpha_prior + cfg.beta_prior)
    confidence = min(100.0, max(0.0, effective_sample / cfg.confidence_threshold * 100))
    return {
        "alpha": round(alpha, 4),
        "beta": round(beta_param, 4),
        "mastery": round(mastery, 1),
        "confidence": round(confidence, 1),
        "active_events": active,
    }


def compute_repeat_discount(days_since_last: float) -> float:
    """Time-based discount for repeat attempts on the same item_id.

    Same day: 0.30 (heavy discount — likely remembers answers)
    1 week:   0.51
    2 weeks:  0.65
    1 month:  0.84
    2 months: ~1.0
    """
    return min(1.0, 0.3 + 0.7 * (1 - 2 ** (-days_since_last / 14)))


def get_quality_weight(source_type: str) -> float:
    """Look up the evidence quality weight for a source type."""
    return QUALITY_WEIGHTS.get(source_type, 1.0)


# ─── DB operations ────────────────────────────────────────────────────


async def invalidate_previous_events(
    db: AsyncSession,
    user_id: uuid.UUID,
    node_id: uuid.UUID,
    source_type: str,
) -> int:
    """Invalidate all active events for this user+node+source_type.

    Used when a student retakes a test/feynman for the same lesson.
    Returns the count of invalidated events.
    """
    result = await db.execute(
        update(EvidenceEvent)
        .where(
            EvidenceEvent.user_id == user_id,
            EvidenceEvent.node_id == node_id,
            EvidenceEvent.source_type == source_type,
            EvidenceEvent.invalidated.is_(False),
        )
        .values(invalidated=True)
    )
    return result.rowcount  # type: ignore[return-value]


async def invalidate_all_lesson_events(
    db: AsyncSession,
    user_id: uuid.UUID,
    node_id: uuid.UUID,
) -> int:
    """Invalidate ALL events for a user+node (used on full lesson reset)."""
    result = await db.execute(
        update(EvidenceEvent)
        .where(
            EvidenceEvent.user_id == user_id,
            EvidenceEvent.node_id == node_id,
            EvidenceEvent.invalidated.is_(False),
        )
        .values(invalidated=True)
    )
    return result.rowcount  # type: ignore[return-value]


async def get_last_attempt_timestamp(
    db: AsyncSession,
    user_id: uuid.UUID,
    item_id: str,
) -> datetime | None:
    """Get the timestamp of the most recent event for an item_id (for repeat discount calc)."""
    result = await db.execute(
        select(EvidenceEvent.timestamp)
        .where(
            EvidenceEvent.user_id == user_id,
            EvidenceEvent.item_id == item_id,
        )
        .order_by(EvidenceEvent.timestamp.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return row


async def get_events_for_node(
    db: AsyncSession,
    user_id: uuid.UUID,
    node_id: uuid.UUID,
) -> list[EvidenceEvent]:
    """Fetch all events for a user+node (including invalidated, for full ledger replay)."""
    result = await db.execute(
        select(EvidenceEvent)
        .where(
            EvidenceEvent.user_id == user_id,
            EvidenceEvent.node_id == node_id,
        )
        .order_by(EvidenceEvent.timestamp)
    )
    return list(result.scalars().all())


async def recalculate_mastery(
    db: AsyncSession,
    user_id: uuid.UUID,
    node_id: uuid.UUID,
) -> float:
    """Recalculate mastery for a user+node and update roadmap_progress.

    Returns the new mastery value (0-100).
    """
    from src.roadmap.models import RoadmapNode, RoadmapProgress

    events = await get_events_for_node(db, user_id, node_id)
    result = compute_mastery_from_events(events)
    mastery = result["mastery"]
    confidence = result["confidence"]

    # Upsert roadmap_progress
    progress_row = await db.execute(
        select(RoadmapProgress).where(
            RoadmapProgress.user_id == user_id,
            RoadmapProgress.node_id == node_id,
        )
    )
    rp = progress_row.scalar_one_or_none()
    if rp:
        rp.mastery = mastery
        rp.confidence = confidence
        rp.progress = round(mastery)
    else:
        rp = RoadmapProgress(
            user_id=user_id,
            node_id=node_id,
            mastery=mastery,
            confidence=confidence,
            progress=round(mastery),
        )
        db.add(rp)

    # Sync mastery to LessonProgress
    from src.learning.models import LessonProgress

    node = await db.get(RoadmapNode, node_id)
    if node and node.lesson_id:
        lp_result = await db.execute(
            select(LessonProgress).where(
                LessonProgress.lesson_id == node.lesson_id,
                LessonProgress.user_id == user_id,
            )
        )
        lp = lp_result.scalar_one_or_none()
        if lp:
            lp.mastery = mastery

    # Push SSE update for live roadmap refresh
    from src.roadmap.progress_bus import ProgressUpdate as BusUpdate, progress_bus
    if node:
        progress_bus.notify(BusUpdate(
            node_id=node_id,
            folder_id=node.folder_id,
            mastery=mastery,
            confidence=confidence,
            stars=rp.stars if rp else 0,
        ))

    return mastery


async def emit_evidence_events(
    db: AsyncSession,
    user_id: uuid.UUID,
    node_id: uuid.UUID,
    source_type: str,
    source_id: uuid.UUID,
    attempt_id: uuid.UUID,
    items: list[dict],
    invalidate_previous: bool = True,
) -> list[EvidenceEvent]:
    """Create evidence events and optionally invalidate previous attempt.

    Args:
        items: list of dicts with keys: item_id, score (0-1)
        invalidate_previous: if True, invalidate prev events of same source_type

    Returns created events.
    """
    now = datetime.now(timezone.utc)

    # Count previous attempts for this source type
    prev_count_result = await db.execute(
        select(EvidenceEvent.attempt_number)
        .where(
            EvidenceEvent.user_id == user_id,
            EvidenceEvent.node_id == node_id,
            EvidenceEvent.source_type == source_type,
        )
        .distinct()
        .order_by(EvidenceEvent.attempt_number.desc())
        .limit(1)
    )
    prev_max = prev_count_result.scalar_one_or_none() or 0
    attempt_number = prev_max + 1

    if invalidate_previous and attempt_number > 1:
        await invalidate_previous_events(db, user_id, node_id, source_type)

    q = get_quality_weight(source_type)
    created: list[EvidenceEvent] = []

    for item in items:
        item_id = item["item_id"]
        score = float(item["score"])

        # Compute repeat discount
        discount = 1.0
        if attempt_number > 1:
            last_ts = await get_last_attempt_timestamp(db, user_id, item_id)
            if last_ts:
                days_gap = (now - last_ts).total_seconds() / 86400
                discount = compute_repeat_discount(days_gap)

        ev = EvidenceEvent(
            user_id=user_id,
            node_id=node_id,
            item_id=item_id,
            source_type=source_type,
            source_id=source_id,
            attempt_id=attempt_id,
            attempt_number=attempt_number,
            score=score,
            quality_weight=q,
            repeat_discount=discount,
            timestamp=now,
        )
        db.add(ev)
        created.append(ev)

    return created
