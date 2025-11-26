"""
Question Bank Service
Business logic for question bank operations including CRUD, import/export functionality.
"""
from django.db import transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404

from courses.models import (
    QuestionBank, QuestionBankQuestion, QuestionBankAnswer,
    Course, Lesson, QuizQuestion, QuizAnswer,
    FinalCourseAssessment, AssessmentQuestion, AssessmentAnswer
)


def get_question_banks(teacher, course_id=None):
    """
    Get all question banks for a teacher, optionally filtered by course.
    
    Args:
        teacher: User instance (teacher)
        course_id: Optional course ID to filter by
    
    Returns:
        QuerySet of QuestionBank objects
    """
    question_banks = QuestionBank.objects.filter(teacher=teacher)
    
    if course_id:
        question_banks = question_banks.filter(course_id=course_id)
    
    return question_banks


def create_question_bank(teacher, name, description='', course_id=None, is_active=True):
    """
    Create a new question bank for a teacher.
    
    Args:
        teacher: User instance (teacher)
        name: Question bank name (required)
        description: Optional description
        course_id: Optional course ID to associate with
        is_active: Whether the bank is active (default: True)
    
    Returns:
        tuple: (success: bool, message: str, question_bank: QuestionBank or None)
    """
    if not name:
        return False, "Question bank name is required.", None
    
    course = None
    if course_id:
        try:
            course = Course.objects.get(id=course_id, instructor=teacher)
        except Course.DoesNotExist:
            return False, "Course not found or you are not the instructor.", None
    
    question_bank = QuestionBank.objects.create(
        teacher=teacher,
        name=name,
        description=description,
        course=course,
        is_active=is_active
    )
    
    return True, "Question bank created successfully.", question_bank


def get_question_bank(bank_id, teacher):
    """
    Get a specific question bank by ID, ensuring teacher ownership.
    
    Args:
        bank_id: Question bank ID
        teacher: User instance (teacher)
    
    Returns:
        QuestionBank instance
    
    Raises:
        QuestionBank.DoesNotExist: If bank not found or not owned by teacher
    """
    return QuestionBank.objects.get(id=bank_id, teacher=teacher)


def update_question_bank(question_bank, teacher, **kwargs):
    """
    Update a question bank.
    
    Args:
        question_bank: QuestionBank instance
        teacher: User instance (teacher)
        **kwargs: Fields to update (name, description, course_id, is_active)
    
    Returns:
        tuple: (success: bool, message: str, question_bank: QuestionBank or None)
    """
    # Check course ownership if course_id is being updated
    if 'course_id' in kwargs:
        course_id = kwargs.pop('course_id')
        if course_id is not None:
            if course_id:
                try:
                    course = Course.objects.get(id=course_id, instructor=teacher)
                    question_bank.course = course
                except Course.DoesNotExist:
                    return False, "Course not found or you are not the instructor.", None
            else:
                question_bank.course = None
    
    # Update other fields
    for field, value in kwargs.items():
        if hasattr(question_bank, field):
            setattr(question_bank, field, value)
    
    question_bank.save()
    return True, "Question bank updated successfully.", question_bank


def delete_question_bank(bank_id, teacher):
    """
    Delete a question bank.
    
    Args:
        bank_id: Question bank ID
        teacher: User instance (teacher)
    
    Returns:
        tuple: (success: bool, message: str)
    
    Raises:
        QuestionBank.DoesNotExist: If bank not found or not owned by teacher
    """
    question_bank = QuestionBank.objects.get(id=bank_id, teacher=teacher)
    question_bank.delete()
    return True, "Question bank deleted successfully."


def get_question_bank_questions(question_bank):
    """
    Get all questions in a question bank.
    
    Args:
        question_bank: QuestionBank instance
    
    Returns:
        QuerySet of QuestionBankQuestion objects
    """
    return QuestionBankQuestion.objects.filter(question_bank=question_bank)


def create_question_bank_question(question_bank, question_data):
    """
    Create a new question in a question bank.
    
    Args:
        question_bank: QuestionBank instance
        question_data: Dict with question fields:
            - question_type
            - question_text
            - question_image (optional)
            - explanation (optional)
            - points (default: 1)
            - order (default: 0)
            - blanks (optional, for fill-blank questions)
            - answers (optional list, for multiple-choice/true-false)
    
    Returns:
        QuestionBankQuestion instance
    """
    question = QuestionBankQuestion.objects.create(
        question_bank=question_bank,
        question_type=question_data.get('question_type', 'multiple-choice'),
        question_text=question_data.get('question_text', ''),
        question_image=question_data.get('question_image'),
        explanation=question_data.get('explanation', ''),
        points=question_data.get('points', 1),
        order=question_data.get('order', 0),
        blanks=question_data.get('blanks', [])
    )
    
    # Create answers if provided (for multiple-choice/true-false)
    answers = question_data.get('answers', [])
    if isinstance(answers, list):
        bulk_answers = []
        for idx, ans_data in enumerate(answers):
            bulk_answers.append(QuestionBankAnswer(
                question=question,
                answer_text=ans_data.get('answer_text') or ans_data.get('text', ''),
                answer_image=ans_data.get('answer_image'),
                is_correct=bool(ans_data.get('is_correct', False)),
                order=ans_data.get('order', idx)
            ))
        if bulk_answers:
            QuestionBankAnswer.objects.bulk_create(bulk_answers)
    
    return question


def get_question_bank_question(bank_id, question_id, teacher):
    """
    Get a specific question from a question bank, ensuring ownership.
    
    Args:
        bank_id: Question bank ID
        question_id: Question ID
        teacher: User instance (teacher)
    
    Returns:
        QuestionBankQuestion instance
    
    Raises:
        QuestionBank.DoesNotExist: If bank not found or not owned by teacher
        QuestionBankQuestion.DoesNotExist: If question not found
    """
    question_bank = QuestionBank.objects.get(id=bank_id, teacher=teacher)
    return QuestionBankQuestion.objects.get(id=question_id, question_bank=question_bank)


def update_question_bank_question(question, question_data):
    """
    Update a question in a question bank.
    
    Args:
        question: QuestionBankQuestion instance
        question_data: Dict with fields to update
    
    Returns:
        QuestionBankQuestion instance
    """
    # Update question fields
    for field in ['question_type', 'question_text', 'question_image', 'explanation', 'points', 'order', 'blanks']:
        if field in question_data:
            setattr(question, field, question_data[field])
    question.save()
    
    # Update answers if provided
    if 'answers' in question_data and isinstance(question_data['answers'], list):
        QuestionBankAnswer.objects.filter(question=question).delete()
        bulk_answers = []
        for idx, ans_data in enumerate(question_data['answers']):
            bulk_answers.append(QuestionBankAnswer(
                question=question,
                answer_text=ans_data.get('answer_text') or ans_data.get('text', ''),
                answer_image=ans_data.get('answer_image'),
                is_correct=bool(ans_data.get('is_correct', False)),
                order=ans_data.get('order', idx)
            ))
        if bulk_answers:
            QuestionBankAnswer.objects.bulk_create(bulk_answers)
    
    return question


def delete_question_bank_question(bank_id, question_id, teacher):
    """
    Delete a question from a question bank.
    
    Args:
        bank_id: Question bank ID
        question_id: Question ID
        teacher: User instance (teacher)
    
    Returns:
        tuple: (success: bool, message: str)
    
    Raises:
        QuestionBank.DoesNotExist: If bank not found or not owned by teacher
        QuestionBankQuestion.DoesNotExist: If question not found
    """
    question_bank = QuestionBank.objects.get(id=bank_id, teacher=teacher)
    question = QuestionBankQuestion.objects.get(id=question_id, question_bank=question_bank)
    question.delete()
    return True, "Question deleted successfully."


def export_questions_to_quiz_lesson(question_bank, lesson, teacher, question_ids=None):
    """
    Export questions from a question bank to a quiz lesson.
    
    Args:
        question_bank: QuestionBank instance
        lesson: Lesson instance (must be a quiz lesson)
        teacher: User instance (teacher)
        question_ids: Optional list of question IDs to export. If None, exports all.
    
    Returns:
        tuple: (success: bool, message: str, data: dict or None)
    """
    # Verify the lesson belongs to a course where the user is the instructor
    if lesson.course.instructor != teacher and not teacher.is_staff:
        return False, "You are not authorized to export questions to this lesson.", None
    
    # Verify it's a quiz lesson
    if lesson.content_type != Lesson.ContentType.QUIZ:
        return False, "This lesson is not a quiz lesson.", None
    
    # Get questions to export
    if question_ids:
        bank_questions = QuestionBankQuestion.objects.filter(
            id__in=question_ids,
            question_bank=question_bank
        )
    else:
        bank_questions = QuestionBankQuestion.objects.filter(question_bank=question_bank)
    
    if not bank_questions.exists():
        return False, "No questions found to export.", None
    
    exported_count = 0
    
    with transaction.atomic():
        # Get the current max order for the lesson
        max_order = QuizQuestion.objects.filter(lesson=lesson).aggregate(
            max_order=Max('order')
        )['max_order'] or -1
        
        for bank_question in bank_questions:
            # Create quiz question
            quiz_question = QuizQuestion.objects.create(
                lesson=lesson,
                question_type=bank_question.question_type,
                question_text=bank_question.question_text,
                question_image=bank_question.question_image,
                explanation=bank_question.explanation,
                points=bank_question.points,
                order=max_order + 1 + exported_count,
                blanks=bank_question.blanks
            )
            
            # Copy answers
            bank_answers = QuestionBankAnswer.objects.filter(question=bank_question)
            quiz_answers = []
            for bank_answer in bank_answers:
                quiz_answers.append(QuizAnswer(
                    question=quiz_question,
                    answer_text=bank_answer.answer_text,
                    answer_image=bank_answer.answer_image,
                    is_correct=bank_answer.is_correct,
                    order=bank_answer.order
                ))
            if quiz_answers:
                QuizAnswer.objects.bulk_create(quiz_answers)
            
            exported_count += 1
    
    return True, f"Successfully exported {exported_count} question(s) to quiz lesson.", {
        "exported_count": exported_count,
        "lesson_id": lesson.id,
        "lesson_title": lesson.title
    }


def export_questions_to_assessment(question_bank, course, teacher, question_ids=None):
    """
    Export questions from a question bank to a final course assessment.
    Creates the assessment if it doesn't exist.
    
    Args:
        question_bank: QuestionBank instance
        course: Course instance
        teacher: User instance (teacher)
        question_ids: Optional list of question IDs to export. If None, exports all.
    
    Returns:
        tuple: (success: bool, message: str, data: dict or None)
    """
    # Get or create final assessment
    final_assessment, created = FinalCourseAssessment.objects.get_or_create(
        course=course,
        defaults={
            'title': f"Final Assessment - {course.title}",
            'description': f"Final assessment for {course.title}",
            'passing_score': 70,
            'max_attempts': 3,
            'time_limit': 60,
            'randomize_questions': True,
            'show_correct_answers': True,
            'is_active': True
        }
    )
    
    # Get questions to export
    if question_ids:
        bank_questions = QuestionBankQuestion.objects.filter(
            id__in=question_ids,
            question_bank=question_bank
        )
    else:
        bank_questions = QuestionBankQuestion.objects.filter(question_bank=question_bank)
    
    if not bank_questions.exists():
        return False, "No questions found to export.", None
    
    exported_count = 0
    
    with transaction.atomic():
        # Get the current max order for the assessment
        max_order = AssessmentQuestion.objects.filter(assessment=final_assessment).aggregate(
            max_order=Max('order')
        )['max_order'] or -1
        
        for bank_question in bank_questions:
            # Create assessment question
            assessment_question = AssessmentQuestion.objects.create(
                assessment=final_assessment,
                question_type=bank_question.question_type,
                question_text=bank_question.question_text,
                question_image=bank_question.question_image,
                explanation=bank_question.explanation,
                points=bank_question.points,
                order=max_order + 1 + exported_count,
                blanks=bank_question.blanks
            )
            
            # Copy answers
            bank_answers = QuestionBankAnswer.objects.filter(question=bank_question)
            assessment_answers = []
            for bank_answer in bank_answers:
                assessment_answers.append(AssessmentAnswer(
                    question=assessment_question,
                    answer_text=bank_answer.answer_text,
                    answer_image=bank_answer.answer_image,
                    is_correct=bank_answer.is_correct,
                    order=bank_answer.order
                ))
            if assessment_answers:
                AssessmentAnswer.objects.bulk_create(assessment_answers)
            
            exported_count += 1
    
    return True, f"Successfully exported {exported_count} question(s) to final assessment.", {
        "exported_count": exported_count,
        "assessment_id": final_assessment.id,
        "assessment_title": final_assessment.title,
        "course_id": course.id
    }


def import_questions_from_quiz_lesson(question_bank, lesson, teacher, question_ids=None):
    """
    Import questions from a quiz lesson to a question bank.
    
    Args:
        question_bank: QuestionBank instance
        lesson: Lesson instance (must be a quiz lesson)
        teacher: User instance (teacher)
        question_ids: Optional list of question IDs to import. If None, imports all.
    
    Returns:
        tuple: (success: bool, message: str, data: dict or None)
    """
    # Verify the lesson belongs to a course where the user is the instructor
    if lesson.course.instructor != teacher and not teacher.is_staff:
        return False, "You are not authorized to import questions from this lesson.", None
    
    # Verify it's a quiz lesson
    if lesson.content_type != Lesson.ContentType.QUIZ:
        return False, "This lesson is not a quiz lesson.", None
    
    # Get questions to import
    if question_ids:
        quiz_questions = QuizQuestion.objects.filter(id__in=question_ids, lesson=lesson)
    else:
        quiz_questions = QuizQuestion.objects.filter(lesson=lesson)
    
    if not quiz_questions.exists():
        return False, "No questions found to import.", None
    
    imported_count = 0
    
    with transaction.atomic():
        # Get the current max order for the question bank
        max_order = QuestionBankQuestion.objects.filter(question_bank=question_bank).aggregate(
            max_order=Max('order')
        )['max_order'] or -1
        
        for quiz_question in quiz_questions:
            # Create bank question
            bank_question = QuestionBankQuestion.objects.create(
                question_bank=question_bank,
                question_type=quiz_question.question_type,
                question_text=quiz_question.question_text,
                question_image=quiz_question.question_image,
                explanation=quiz_question.explanation,
                points=quiz_question.points,
                order=max_order + 1 + imported_count,
                blanks=quiz_question.blanks
            )
            
            # Copy answers
            quiz_answers = QuizAnswer.objects.filter(question=quiz_question)
            bank_answers = []
            for quiz_answer in quiz_answers:
                bank_answers.append(QuestionBankAnswer(
                    question=bank_question,
                    answer_text=quiz_answer.answer_text,
                    answer_image=quiz_answer.answer_image,
                    is_correct=quiz_answer.is_correct,
                    order=quiz_answer.order
                ))
            if bank_answers:
                QuestionBankAnswer.objects.bulk_create(bank_answers)
            
            imported_count += 1
    
    return True, f"Successfully imported {imported_count} question(s) to question bank.", {
        "imported_count": imported_count,
        "question_bank_id": question_bank.id,
        "question_bank_name": question_bank.name,
        "lesson_id": lesson.id
    }


def import_questions_from_assessment(question_bank, course, teacher, question_ids=None):
    """
    Import questions from a final course assessment to a question bank.
    
    Args:
        question_bank: QuestionBank instance
        course: Course instance
        teacher: User instance (teacher)
        question_ids: Optional list of question IDs to import. If None, imports all.
    
    Returns:
        tuple: (success: bool, message: str, data: dict or None)
    """
    try:
        final_assessment = FinalCourseAssessment.objects.get(course=course)
    except FinalCourseAssessment.DoesNotExist:
        return False, "Final assessment not found for this course.", None
    
    # Get questions to import
    if question_ids:
        assessment_questions = AssessmentQuestion.objects.filter(
            id__in=question_ids,
            assessment=final_assessment
        )
    else:
        assessment_questions = AssessmentQuestion.objects.filter(assessment=final_assessment)
    
    if not assessment_questions.exists():
        return False, "No questions found to import.", None
    
    imported_count = 0
    
    with transaction.atomic():
        # Get the current max order for the question bank
        max_order = QuestionBankQuestion.objects.filter(question_bank=question_bank).aggregate(
            max_order=Max('order')
        )['max_order'] or -1
        
        for assessment_question in assessment_questions:
            # Create bank question
            bank_question = QuestionBankQuestion.objects.create(
                question_bank=question_bank,
                question_type=assessment_question.question_type,
                question_text=assessment_question.question_text,
                question_image=assessment_question.question_image,
                explanation=assessment_question.explanation,
                points=assessment_question.points,
                order=max_order + 1 + imported_count,
                blanks=assessment_question.blanks
            )
            
            # Copy answers
            assessment_answers = AssessmentAnswer.objects.filter(question=assessment_question)
            bank_answers = []
            for assessment_answer in assessment_answers:
                bank_answers.append(QuestionBankAnswer(
                    question=bank_question,
                    answer_text=assessment_answer.answer_text,
                    answer_image=assessment_answer.answer_image,
                    is_correct=assessment_answer.is_correct,
                    order=assessment_answer.order
                ))
            if bank_answers:
                QuestionBankAnswer.objects.bulk_create(bank_answers)
            
            imported_count += 1
    
    return True, f"Successfully imported {imported_count} question(s) to question bank.", {
        "imported_count": imported_count,
        "question_bank_id": question_bank.id,
        "question_bank_name": question_bank.name,
        "assessment_id": final_assessment.id
    }

