from src.learning.feedback.service import _build_fingerprint, _is_probable_duplicate
from src.learning.feynman.prompts import EVALUATOR_SYSTEM
from src.learning.tests.prompts import GRADING_SYSTEM


def test_grading_prompt_requests_only_high_impact_feedback_notes() -> None:
    assert "ONLY for high-impact conceptual mistakes" in GRADING_SYSTEM
    assert "Return at most 2 feedback_notes total" in GRADING_SYSTEM
    assert "Use only these severities in feedback_notes: moderate or critical." in GRADING_SYSTEM


def test_feynman_prompt_requests_only_high_impact_feedback_notes() -> None:
    assert "ONLY for substantial conceptual mistakes" in EVALUATOR_SYSTEM
    assert "Return at most 2 feedback_notes total" in EVALUATOR_SYSTEM
    assert "Use only moderate or critical severity for feedback_notes." in EVALUATOR_SYSTEM


def test_duplicate_detection_handles_paraphrased_same_mistake() -> None:
    first = _build_fingerprint(
        topic="Price elasticity of demand",
        mistake="Student says demand is inelastic because quantity changed a lot.",
        correction="Demand is elastic because quantity changes proportionally more than price.",
    )
    second = _build_fingerprint(
        topic="Demand price elasticity",
        mistake="Student calls demand inelastic even though quantity changes by a larger percentage.",
        correction="Demand is elastic because quantity changes by a larger percentage than price.",
    )

    assert _is_probable_duplicate(first, second)


def test_duplicate_detection_keeps_distinct_concepts() -> None:
    first = _build_fingerprint(
        topic="Price elasticity of demand",
        mistake="Confuses elastic and inelastic demand.",
        correction="Elastic means quantity changes more than price.",
    )
    second = _build_fingerprint(
        topic="Fiscal policy",
        mistake="States that contractionary policy increases aggregate demand.",
        correction="Contractionary policy reduces aggregate demand.",
    )

    assert not _is_probable_duplicate(first, second)


def test_feedback_note_model_has_folder_id() -> None:
    from src.learning.feedback.models import FeedbackNote
    col = FeedbackNote.__table__.c.get("folder_id")
    assert col is not None, "FeedbackNote.folder_id column missing"
    assert col.nullable is True


def test_lesson_model_has_folder_id() -> None:
    from src.learning.models import Lesson
    col = Lesson.__table__.c.get("folder_id")
    assert col is not None, "Lesson.folder_id column missing"
    assert col.nullable is True


def test_feedback_note_service_has_resolve_folder_id_method() -> None:
    import inspect
    from src.learning.feedback.service import FeedbackNoteService
    assert hasattr(FeedbackNoteService, "_resolve_folder_id"), \
        "FeedbackNoteService._resolve_folder_id method missing"
    sig = inspect.signature(FeedbackNoteService._resolve_folder_id)
    assert "source_type" in sig.parameters
    assert "source_session_id" in sig.parameters


def test_list_for_user_accepts_folder_id_param() -> None:
    import inspect
    from src.learning.feedback.service import FeedbackNoteService
    sig = inspect.signature(FeedbackNoteService.list_for_user)
    assert "folder_id" in sig.parameters, \
        "list_for_user() missing folder_id parameter"
    assert sig.parameters["folder_id"].default is None


def test_get_summary_accepts_folder_id_param() -> None:
    import inspect
    from src.learning.feedback.service import FeedbackNoteService
    sig = inspect.signature(FeedbackNoteService.get_summary)
    assert "folder_id" in sig.parameters, \
        "get_summary() missing folder_id parameter"
    assert sig.parameters["folder_id"].default is None


def test_feedback_note_out_schema_includes_folder_id() -> None:
    import uuid
    from datetime import datetime, timezone
    from src.learning.feedback.schemas import FeedbackNoteOut

    note = FeedbackNoteOut(
        id=uuid.uuid4(),
        source_type="test",
        source_session_id=uuid.uuid4(),
        source_answer_id=None,
        severity="moderate",
        topic="Elasticity",
        mistake="Confused elastic with inelastic",
        correction="Elastic means quantity changes more than price",
        status="see",
        review_question=None,
        created_at=datetime.now(tz=timezone.utc),
        folder_id=None,
    )
    assert note.folder_id is None

    folder_id = uuid.uuid4()
    note2 = FeedbackNoteOut(
        id=uuid.uuid4(),
        source_type="test",
        source_session_id=uuid.uuid4(),
        source_answer_id=None,
        severity="moderate",
        topic="Elasticity",
        mistake="Confused elastic with inelastic",
        correction="Elastic means quantity changes more than price",
        status="see",
        review_question=None,
        created_at=datetime.now(tz=timezone.utc),
        folder_id=folder_id,
    )
    assert note2.folder_id == folder_id
