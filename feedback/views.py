from typing import Any, Dict, List

from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone
from django.shortcuts import get_object_or_404

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from feedback.models import (
    FeedbackForm,
    FeedbackQuestion,
    FeedbackQuestionOption,
    FeedbackSubmission,
    FeedbackAnswer,
)


def _is_teacher(user) -> bool:
    """
    Returns True if user is a teacher or staff.
    """
    if getattr(user, "is_staff", False):
        return True
    role = getattr(user, "role", None)
    return bool(role and getattr(role, "name", "").lower() == "teacher")


def _is_student(user) -> bool:
    if getattr(user, "is_staff", False):
        return True
    role = getattr(user, "role", None)
    return bool(role and getattr(role, "name", "").lower() == "student")


def _serialize_option(option: FeedbackQuestionOption) -> Dict[str, Any]:
    return {
        "id": option.id,
        "option_label": option.option_label,
        "option_value": option.option_value,
        "sort_order": option.sort_order,
    }


def _serialize_question(question: FeedbackQuestion) -> Dict[str, Any]:
    return {
        "id": question.id,
        "form_id": question.form_id,
        "question_text": question.question_text,
        "question_type": question.question_type,
        "is_required": question.is_required,
        "sort_order": question.sort_order,
        "settings_json": question.settings_json or {},
        "options": [_serialize_option(opt) for opt in question.options.all()],
    }


def _serialize_form(form: FeedbackForm, include_questions: bool = True) -> Dict[str, Any]:
    data = {
        "id": form.id,
        "title": form.title,
        "description": form.description,
        "created_by": form.created_by_id,
        "target_type": form.target_type,
        "target_id": form.target_id,
        "is_published": form.is_published,
        "allow_anonymous": form.allow_anonymous,
        "allow_multiple_submissions": form.allow_multiple_submissions,
        "start_at": form.start_at,
        "end_at": form.end_at,
        "created_at": form.created_at,
        "updated_at": form.updated_at,
        "is_active": form.is_active,
    }
    if include_questions:
        questions = form.questions.all().order_by("sort_order", "id").prefetch_related(
            "options"
        )
        data["questions"] = [_serialize_question(q) for q in questions]
    return data


def _serialize_answer(answer: FeedbackAnswer) -> Dict[str, Any]:
    return {
        "id": answer.id,
        "question_id": answer.question_id,
        "answer_text": answer.answer_text,
        "answer_number": answer.answer_number,
        "answer_bool": answer.answer_bool,
        "answer_json": answer.answer_json or {},
    }


def _serialize_submission(submission: FeedbackSubmission) -> Dict[str, Any]:
    answers = submission.answers.select_related("question").all()
    return {
        "id": submission.id,
        "form_id": submission.form_id,
        "student_id": submission.student_id,
        "status": submission.status,
        "submitted_at": submission.submitted_at,
        "created_at": submission.created_at,
        "updated_at": submission.updated_at,
        "answers": [_serialize_answer(a) for a in answers],
    }


# ---------------------------------------------------------------------------
# Teacher APIs
# ---------------------------------------------------------------------------


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_feedback_form_view(request):
    """
    POST /api/teacher/feedback/forms
    Create a new feedback form owned by the authenticated teacher.
    """
    user = request.user
    if not _is_teacher(user):
        return Response(
            {"success": False, "message": "Only teachers can create feedback forms."},
            status=status.HTTP_403_FORBIDDEN,
        )

    payload = request.data or {}
    title = payload.get("title", "").strip()
    description = payload.get("description", "").strip()
    target_type = (payload.get("target_type") or "global").strip().lower()
    target_id = payload.get("target_id") or 0
    allow_anonymous = bool(payload.get("allow_anonymous", False))
    allow_multiple_submissions = bool(payload.get("allow_multiple_submissions", False))
    start_at = payload.get("start_at")
    end_at = payload.get("end_at")

    if not title:
        return Response(
            {"success": False, "message": "Title is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if target_type not in dict(FeedbackForm.TARGET_TYPE_CHOICES):
        return Response(
            {"success": False, "message": "Invalid target_type."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        target_id = int(target_id)
    except (TypeError, ValueError):
        target_id = 0

    form = FeedbackForm.objects.create(
        title=title,
        description=description,
        created_by=user,
        target_type=target_type,
        target_id=target_id,
        allow_anonymous=allow_anonymous,
        allow_multiple_submissions=allow_multiple_submissions,
        start_at=start_at,
        end_at=end_at,
        is_published=False,
    )

    return Response(
        {"success": True, "data": _serialize_form(form), "message": "Feedback form created."},
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_feedback_forms_view(request):
    """
    GET /api/teacher/feedback/forms
    List feedback forms created by the teacher (or all for admins).
    """
    user = request.user
    if not _is_teacher(user):
        return Response(
            {"success": False, "message": "Only teachers can view their feedback forms."},
            status=status.HTTP_403_FORBIDDEN,
        )

    qs = FeedbackForm.objects.all().order_by("-created_at")
    if not user.is_staff:
        qs = qs.filter(created_by=user)

    qs = qs.prefetch_related("questions__options")
    data = [_serialize_form(f) for f in qs]
    return Response(
        {"success": True, "data": data, "message": "Feedback forms retrieved."},
        status=status.HTTP_200_OK,
    )


def _get_owned_form(user, form_id: int) -> FeedbackForm:
    form = get_object_or_404(FeedbackForm, id=form_id)
    if not (user.is_staff or form.created_by_id == user.id):
        raise PermissionError("You are not allowed to access this feedback form.")
    return form


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def retrieve_feedback_form_view(request, form_id: int):
    """
    GET /api/teacher/feedback/forms/{id}
    Retrieve a single feedback form with its questions.
    """
    user = request.user
    if not _is_teacher(user):
        return Response(
            {"success": False, "message": "Only teachers can view feedback forms."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        form = _get_owned_form(user, form_id)
    except PermissionError as e:
        return Response(
            {"success": False, "message": str(e)},
            status=status.HTTP_403_FORBIDDEN,
        )
    except FeedbackForm.DoesNotExist:
        return Response(
            {"success": False, "message": "Feedback form not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    form = FeedbackForm.objects.filter(id=form.id).prefetch_related(
        "questions__options"
    ).first()
    return Response(
        {"success": True, "data": _serialize_form(form), "message": "Feedback form retrieved."},
        status=status.HTTP_200_OK,
    )


@api_view(["PUT", "PATCH"])
@permission_classes([IsAuthenticated])
def update_feedback_form_view(request, form_id: int):
    """
    PUT /api/teacher/feedback/forms/{id}
    Update basic properties of a feedback form (not questions).
    """
    user = request.user
    if not _is_teacher(user):
        return Response(
            {"success": False, "message": "Only teachers can update feedback forms."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        form = _get_owned_form(user, form_id)
    except PermissionError as e:
        return Response(
            {"success": False, "message": str(e)},
            status=status.HTTP_403_FORBIDDEN,
        )
    except FeedbackForm.DoesNotExist:
        return Response(
            {"success": False, "message": "Feedback form not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    payload = request.data or {}
    for field in [
        "title",
        "description",
        "allow_anonymous",
        "allow_multiple_submissions",
        "start_at",
        "end_at",
    ]:
        if field in payload:
            setattr(form, field, payload[field])

    form.save()
    form.refresh_from_db()

    form = FeedbackForm.objects.filter(id=form.id).prefetch_related(
        "questions__options"
    ).first()
    return Response(
        {"success": True, "data": _serialize_form(form), "message": "Feedback form updated."},
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_feedback_question_view(request, form_id: int):
    """
    POST /api/teacher/feedback/forms/{id}/questions
    Add a question (and optional options) to a form.
    """
    user = request.user
    if not _is_teacher(user):
        return Response(
            {"success": False, "message": "Only teachers can manage feedback questions."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        form = _get_owned_form(user, form_id)
    except PermissionError as e:
        return Response(
            {"success": False, "message": str(e)},
            status=status.HTTP_403_FORBIDDEN,
        )
    except FeedbackForm.DoesNotExist:
        return Response(
            {"success": False, "message": "Feedback form not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    payload = request.data or {}
    question_text = (payload.get("question_text") or "").strip()
    question_type = (payload.get("question_type") or "").strip()
    is_required = bool(payload.get("is_required", False))
    sort_order = payload.get("sort_order")
    settings_json = payload.get("settings_json") or {}
    options_payload: List[Dict[str, Any]] = payload.get("options") or []

    if not question_text:
        return Response(
            {"success": False, "message": "question_text is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if question_type not in dict(FeedbackQuestion.QUESTION_TYPE_CHOICES):
        return Response(
            {"success": False, "message": "Invalid question_type."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if sort_order is None:
        agg = form.questions.aggregate(max_sort=Max("sort_order"))
        existing_max = agg.get("max_sort") or 0
        sort_order = existing_max + 1

    if question_type in ("single_choice", "multi_choice"):
        if len(options_payload) < 2:
            return Response(
                {
                    "success": False,
                    "message": "Choice questions must have at least two options.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    if question_type == "rating":
        if not isinstance(settings_json, dict) or "min" not in settings_json or "max" not in settings_json:
            return Response(
                {
                    "success": False,
                    "message": "Rating questions require 'min' and 'max' in settings_json.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    with transaction.atomic():
        question = FeedbackQuestion.objects.create(
            form=form,
            question_text=question_text,
            question_type=question_type,
            is_required=is_required,
            sort_order=sort_order,
            settings_json=settings_json,
        )

        for idx, opt in enumerate(options_payload):
            label = (opt.get("option_label") or "").strip()
            value = (opt.get("option_value") or "").strip() or label
            if not label:
                continue
            FeedbackQuestionOption.objects.create(
                question=question,
                option_label=label,
                option_value=value,
                sort_order=idx,
            )

    question.refresh_from_db()
    question = FeedbackQuestion.objects.filter(id=question.id).prefetch_related(
        "options"
    ).first()
    return Response(
        {"success": True, "data": _serialize_question(question), "message": "Question added."},
        status=status.HTTP_201_CREATED,
    )


@api_view(["PUT", "PATCH"])
@permission_classes([IsAuthenticated])
def update_feedback_question_view(request, question_id: int):
    """
    PUT /api/teacher/feedback/questions/{id}
    Update a feedback question and optionally replace its options.
    """
    user = request.user
    if not _is_teacher(user):
        return Response(
            {"success": False, "message": "Only teachers can manage feedback questions."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        question = FeedbackQuestion.objects.select_related("form").get(id=question_id)
    except FeedbackQuestion.DoesNotExist:
        return Response(
            {"success": False, "message": "Feedback question not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if not (user.is_staff or question.form.created_by_id == user.id):
        return Response(
            {"success": False, "message": "You are not allowed to modify this question."},
            status=status.HTTP_403_FORBIDDEN,
        )

    payload = request.data or {}
    question_text = payload.get("question_text")
    question_type = payload.get("question_type")
    is_required = payload.get("is_required")
    sort_order = payload.get("sort_order")
    settings_json = payload.get("settings_json")
    options_payload: List[Dict[str, Any]] = payload.get("options") or []

    if question_text is not None:
        question.question_text = question_text
    if question_type is not None:
        if question_type not in dict(FeedbackQuestion.QUESTION_TYPE_CHOICES):
            return Response(
                {"success": False, "message": "Invalid question_type."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        question.question_type = question_type
    if is_required is not None:
        question.is_required = bool(is_required)
    if sort_order is not None:
        question.sort_order = sort_order
    if settings_json is not None:
        question.settings_json = settings_json

    effective_type = question.question_type
    if effective_type in ("single_choice", "multi_choice") and options_payload:
        if len(options_payload) < 2:
            return Response(
                {
                    "success": False,
                    "message": "Choice questions must have at least two options.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    if effective_type == "rating":
        sj = question.settings_json or {}
        if not isinstance(sj, dict) or "min" not in sj or "max" not in sj:
            return Response(
                {
                    "success": False,
                    "message": "Rating questions require 'min' and 'max' in settings_json.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    with transaction.atomic():
        question.save()

        if options_payload:
            question.options.all().delete()
            for idx, opt in enumerate(options_payload):
                label = (opt.get("option_label") or "").strip()
                value = (opt.get("option_value") or "").strip() or label
                if not label:
                    continue
                FeedbackQuestionOption.objects.create(
                    question=question,
                    option_label=label,
                    option_value=value,
                    sort_order=idx,
                )

    question = FeedbackQuestion.objects.filter(id=question.id).prefetch_related(
        "options"
    ).first()
    return Response(
        {"success": True, "data": _serialize_question(question), "message": "Question updated."},
        status=status.HTTP_200_OK,
    )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_feedback_question_view(request, question_id: int):
    """
    DELETE /api/teacher/feedback/questions/{id}
    Delete a feedback question.
    """
    user = request.user
    if not _is_teacher(user):
        return Response(
            {"success": False, "message": "Only teachers can manage feedback questions."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        question = FeedbackQuestion.objects.select_related("form").get(id=question_id)
    except FeedbackQuestion.DoesNotExist:
        return Response(
            {"success": False, "message": "Feedback question not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if not (user.is_staff or question.form.created_by_id == user.id):
        return Response(
            {"success": False, "message": "You are not allowed to delete this question."},
            status=status.HTTP_403_FORBIDDEN,
        )

    question.delete()
    return Response(
        {"success": True, "message": "Question deleted."},
        status=status.HTTP_200_OK,
    )


def _validate_form_publishable(form: FeedbackForm) -> str | None:
    """
    Returns an error message if the form cannot be published, else None.
    """
    questions = form.questions.all().prefetch_related("options")
    if not questions:
        return "Cannot publish a form with zero questions."

    for q in questions:
        if q.question_type in ("single_choice", "multi_choice"):
            if q.options.count() < 2:
                return f"Question '{q.question_text[:50]}' must have at least two options."
        if q.question_type == "rating":
            sj = q.settings_json or {}
            if not isinstance(sj, dict) or "min" not in sj or "max" not in sj:
                return f"Rating question '{q.question_text[:50]}' requires 'min' and 'max' in settings_json."
    return None


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def publish_feedback_form_view(request, form_id: int):
    """
    POST /api/teacher/feedback/forms/{id}/publish
    Publish a feedback form after validation.
    """
    user = request.user
    if not _is_teacher(user):
        return Response(
            {"success": False, "message": "Only teachers can publish feedback forms."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        form = _get_owned_form(user, form_id)
    except PermissionError as e:
        return Response(
            {"success": False, "message": str(e)},
            status=status.HTTP_403_FORBIDDEN,
        )
    except FeedbackForm.DoesNotExist:
        return Response(
            {"success": False, "message": "Feedback form not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    error = _validate_form_publishable(form)
    if error:
        return Response(
            {"success": False, "message": error},
            status=status.HTTP_400_BAD_REQUEST,
        )

    form.is_published = True
    form.save(update_fields=["is_published", "updated_at"])
    form = FeedbackForm.objects.filter(id=form.id).prefetch_related(
        "questions__options"
    ).first()
    return Response(
        {"success": True, "data": _serialize_form(form), "message": "Feedback form published."},
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def unpublish_feedback_form_view(request, form_id: int):
    """
    POST /api/teacher/feedback/forms/{id}/unpublish
    Unpublish a feedback form.
    """
    user = request.user
    if not _is_teacher(user):
        return Response(
            {"success": False, "message": "Only teachers can unpublish feedback forms."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        form = _get_owned_form(user, form_id)
    except PermissionError as e:
        return Response(
            {"success": False, "message": str(e)},
            status=status.HTTP_403_FORBIDDEN,
        )
    except FeedbackForm.DoesNotExist:
        return Response(
            {"success": False, "message": "Feedback form not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    form.is_published = False
    form.save(update_fields=["is_published", "updated_at"])
    form = FeedbackForm.objects.filter(id=form.id).prefetch_related(
        "questions__options"
    ).first()
    return Response(
        {"success": True, "data": _serialize_form(form), "message": "Feedback form unpublished."},
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_feedback_form_submissions_view(request, form_id: int):
    """
    GET /api/teacher/feedback/forms/{id}/submissions
    List submissions and answers for a feedback form (teacher/admin only).
    """
    user = request.user
    if not _is_teacher(user):
        return Response(
            {"success": False, "message": "Only teachers can view feedback responses."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        form = _get_owned_form(user, form_id)
    except PermissionError as e:
        return Response(
            {"success": False, "message": str(e)},
            status=status.HTTP_403_FORBIDDEN,
        )
    except FeedbackForm.DoesNotExist:
        return Response(
            {"success": False, "message": "Feedback form not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    submissions = (
        FeedbackSubmission.objects.filter(form=form)
        .select_related("student")
        .prefetch_related("answers__question")
        .order_by("-submitted_at", "-created_at")
    )

    data = [_serialize_submission(s) for s in submissions]
    return Response(
        {"success": True, "data": data, "message": "Feedback submissions retrieved."},
        status=status.HTTP_200_OK,
    )


# ---------------------------------------------------------------------------
# Student APIs
# ---------------------------------------------------------------------------


def _eligible_forms_for_student(user) -> List[FeedbackForm]:
    """
    Returns queryset of forms the student is allowed to see.
    Currently: any published, active form (no course relation).
    """
    now = timezone.now()
    qs = FeedbackForm.objects.filter(
        is_published=True,
    ).filter(
        Q(start_at__isnull=True) | Q(start_at__lte=now),
        Q(end_at__isnull=True) | Q(end_at__gte=now),
    )

    if user.is_staff:
        return qs

    # No course-based filtering: all active, published forms are visible.
    return qs


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_student_feedback_forms_view(request):
    """
    GET /api/student/feedback/forms
    List published, active feedback forms the student is eligible to answer.
    """
    user = request.user
    if not _is_student(user):
        return Response(
            {"success": False, "message": "Only students can access this endpoint."},
            status=status.HTTP_403_FORBIDDEN,
        )

    qs = _eligible_forms_for_student(user).prefetch_related("questions__options")
    data = [_serialize_form(f) for f in qs]
    return Response(
        {"success": True, "data": data, "message": "Available feedback forms retrieved."},
        status=status.HTTP_200_OK,
    )


def _get_student_visible_form(user, form_id: int) -> FeedbackForm:
    qs = _eligible_forms_for_student(user)
    return get_object_or_404(qs, id=form_id)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def retrieve_student_feedback_form_view(request, form_id: int):
    """
    GET /api/student/feedback/forms/{id}
    Retrieve a single feedback form available to the student (with questions).
    """
    user = request.user
    if not _is_student(user):
        return Response(
            {"success": False, "message": "Only students can access this endpoint."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        form = _get_student_visible_form(user, form_id)
    except FeedbackForm.DoesNotExist:
        return Response(
            {"success": False, "message": "Feedback form not found or not available."},
            status=status.HTTP_404_NOT_FOUND,
        )

    form = FeedbackForm.objects.filter(id=form.id).prefetch_related(
        "questions__options"
    ).first()
    return Response(
        {"success": True, "data": _serialize_form(form), "message": "Feedback form retrieved."},
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def submit_student_feedback_form_view(request, form_id: int):
    """
    POST /api/student/feedback/forms/{id}/submit
    Submit answers for a feedback form.
    """
    user = request.user
    if not _is_student(user):
        return Response(
            {"success": False, "message": "Only students can submit feedback."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        form = _get_student_visible_form(user, form_id)
    except FeedbackForm.DoesNotExist:
        return Response(
            {"success": False, "message": "Feedback form not found or not available."},
            status=status.HTTP_404_NOT_FOUND,
        )

    payload = request.data or {}
    answers_payload: List[Dict[str, Any]] = payload.get("answers") or []
    answers_by_qid = {int(a.get("question_id")): a.get("value") for a in answers_payload if a.get("question_id")}

    questions = list(
        form.questions.all().prefetch_related("options").order_by("sort_order", "id")
    )
    missing_required = []

    for q in questions:
        if not q.is_required:
            continue
        if q.id not in answers_by_qid:
            missing_required.append(q.id)

    if missing_required:
        return Response(
            {
                "success": False,
                "message": "Required questions are missing answers.",
                "missing_question_ids": missing_required,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not form.allow_multiple_submissions and not form.allow_anonymous:
        existing = FeedbackSubmission.objects.filter(form=form, student=user).exists()
        if existing:
            return Response(
                {
                    "success": False,
                    "message": "You have already submitted feedback for this form.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    with transaction.atomic():
        submission = FeedbackSubmission.objects.create(
            form=form,
            student=None if form.allow_anonymous else user,
            status="submitted",
            submitted_at=timezone.now(),
        )

        for q in questions:
            if q.id not in answers_by_qid:
                if not q.is_required:
                    continue
            raw_value = answers_by_qid.get(q.id)

            answer_kwargs: Dict[str, Any] = {
                "submission": submission,
                "question": q,
            }

            if q.question_type in ("text", "textarea"):
                answer_kwargs["answer_text"] = "" if raw_value is None else str(raw_value)

            elif q.question_type == "single_choice":
                chosen_option = None
                if raw_value is not None:
                    options = list(q.options.all())
                    try:
                        as_int = int(raw_value)
                        chosen_option = next(
                            (opt for opt in options if opt.id == as_int), None
                        )
                    except (TypeError, ValueError):
                        chosen_option = None
                    if chosen_option is None:
                        chosen_option = next(
                            (
                                opt
                                for opt in options
                                if opt.option_value == str(raw_value)
                            ),
                            None,
                        )
                if chosen_option:
                    answer_kwargs["answer_text"] = chosen_option.option_label
                    answer_kwargs["answer_json"] = {
                        "option_id": chosen_option.id,
                        "option_value": chosen_option.option_value,
                    }

            elif q.question_type == "multi_choice":
                selected = raw_value or []
                if not isinstance(selected, list):
                    selected = [selected]
                options = list(q.options.all())
                chosen_list = []
                for item in selected:
                    opt = None
                    try:
                        as_int = int(item)
                        opt = next((o for o in options if o.id == as_int), None)
                    except (TypeError, ValueError):
                        pass
                    if opt is None:
                        opt = next(
                            (o for o in options if o.option_value == str(item)), None
                        )
                    if opt:
                        chosen_list.append(
                            {
                                "option_id": opt.id,
                                "option_value": opt.option_value,
                                "option_label": opt.option_label,
                            }
                        )
                answer_kwargs["answer_json"] = {"selected_options": chosen_list}

            elif q.question_type == "rating":
                try:
                    num_val = float(raw_value)
                except (TypeError, ValueError):
                    num_val = None
                limits = q.settings_json or {}
                min_v = limits.get("min")
                max_v = limits.get("max")
                if num_val is not None and isinstance(min_v, (int, float)) and isinstance(
                    max_v, (int, float)
                ):
                    if num_val < float(min_v) or num_val > float(max_v):
                        return Response(
                            {
                                "success": False,
                                "message": f"Rating for question {q.id} must be between {min_v} and {max_v}.",
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                answer_kwargs["answer_number"] = num_val

            elif q.question_type == "yes_no":
                if isinstance(raw_value, str):
                    lowered = raw_value.strip().lower()
                    if lowered in ("true", "yes", "1"):
                        bool_val = True
                    elif lowered in ("false", "no", "0"):
                        bool_val = False
                    else:
                        bool_val = None
                else:
                    bool_val = bool(raw_value) if raw_value is not None else None
                answer_kwargs["answer_bool"] = bool_val

            else:
                if isinstance(raw_value, (dict, list)):
                    answer_kwargs["answer_json"] = raw_value
                else:
                    answer_kwargs["answer_text"] = "" if raw_value is None else str(
                        raw_value
                    )

            FeedbackAnswer.objects.create(**answer_kwargs)

    submission = FeedbackSubmission.objects.filter(id=submission.id).prefetch_related(
        "answers__question"
    ).first()
    return Response(
        {
            "success": True,
            "data": _serialize_submission(submission),
            "message": "Feedback submitted successfully.",
        },
        status=status.HTTP_201_CREATED,
    )


