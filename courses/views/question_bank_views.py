from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import Max

from courses.models import (
    QuestionBank, QuestionBankQuestion, QuestionBankAnswer,
    Course, Lesson, QuizQuestion, QuizAnswer,
    FinalCourseAssessment, AssessmentQuestion, AssessmentAnswer
)
from courses.serializers import DynamicFieldSerializer


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def question_banks_list_create_view(request):
    """
    List all question banks for the authenticated teacher or create a new one.
    
    GET: Returns all question banks for the teacher's courses
    POST: Creates a new question bank
    Expected payload: {
        "name": "Python Basics",
        "description": "Questions about Python basics",
        "course_id": 1  // optional
    }
    """
    if request.method == 'GET':
        # Get all question banks for courses where user is the instructor
        question_banks = QuestionBank.objects.filter(teacher=request.user)
        
        # Optional: filter by course
        course_id = request.query_params.get('course_id')
        if course_id:
            question_banks = question_banks.filter(course_id=course_id)
        
        serializer = DynamicFieldSerializer(question_banks, many=True, model_name="questionbank")
        
        return Response({
            "success": True,
            "data": serializer.data,
            "message": "Question banks retrieved successfully."
        }, status=status.HTTP_200_OK)
    
    # POST: Create new question bank
    if request.method == 'POST':
        name = request.data.get('name')
        if not name:
            return Response({
                "success": False,
                "message": "Question bank name is required."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        course_id = request.data.get('course_id')
        course = None
        if course_id:
            try:
                course = Course.objects.get(id=course_id, instructor=request.user)
            except Course.DoesNotExist:
                return Response({
                    "success": False,
                    "message": "Course not found or you are not the instructor."
                }, status=status.HTTP_404_NOT_FOUND)
        
        question_bank = QuestionBank.objects.create(
            teacher=request.user,
            name=name,
            description=request.data.get('description', ''),
            course=course,
            is_active=request.data.get('is_active', True)
        )
        
        serializer = DynamicFieldSerializer(question_bank, model_name="questionbank")
        
        return Response({
            "success": True,
            "data": serializer.data,
            "message": "Question bank created successfully."
        }, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def question_bank_detail_view(request, bank_id):
    """
    Retrieve, update, or delete a question bank.
    """
    question_bank = get_object_or_404(QuestionBank, id=bank_id, teacher=request.user)
    
    if request.method == 'GET':
        serializer = DynamicFieldSerializer(question_bank, model_name="questionbank")
        
        # Include questions count
        data = serializer.data
        data['total_questions'] = question_bank.total_questions
        
        return Response({
            "success": True,
            "data": data,
            "message": "Question bank retrieved successfully."
        }, status=status.HTTP_200_OK)
    
    if request.method == 'PATCH':
        serializer = DynamicFieldSerializer(
            question_bank, 
            data=request.data, 
            partial=True,
            model_name="questionbank"
        )
        
        if serializer.is_valid():
            # Check course ownership if course_id is being updated
            course_id = request.data.get('course_id')
            if course_id is not None:
                if course_id:
                    try:
                        course = Course.objects.get(id=course_id, instructor=request.user)
                        question_bank.course = course
                    except Course.DoesNotExist:
                        return Response({
                            "success": False,
                            "message": "Course not found or you are not the instructor."
                        }, status=status.HTTP_404_NOT_FOUND)
                else:
                    question_bank.course = None
            
            serializer.save()
            return Response({
                "success": True,
                "data": serializer.data,
                "message": "Question bank updated successfully."
            }, status=status.HTTP_200_OK)
        
        return Response({
            "success": False,
            "message": serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    if request.method == 'DELETE':
        question_bank.delete()
        return Response({
            "success": True,
            "message": "Question bank deleted successfully."
        }, status=status.HTTP_200_OK)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def question_bank_questions_list_create_view(request, bank_id):
    """
    List all questions in a question bank or create a new question.
    """
    question_bank = get_object_or_404(QuestionBank, id=bank_id, teacher=request.user)
    
    if request.method == 'GET':
        questions = QuestionBankQuestion.objects.filter(question_bank=question_bank)
        serializer = DynamicFieldSerializer(questions, many=True, model_name="questionbankquestion")
        
        return Response({
            "success": True,
            "data": serializer.data,
            "message": "Questions retrieved successfully."
        }, status=status.HTTP_200_OK)
    
    # POST: Create new question
    if request.method == 'POST':
        data = request.data
        
        question = QuestionBankQuestion.objects.create(
            question_bank=question_bank,
            question_type=data.get('question_type', 'multiple-choice'),
            question_text=data.get('question_text', ''),
            question_image=data.get('question_image'),
            explanation=data.get('explanation', ''),
            points=data.get('points', 1),
            order=data.get('order', 0),
            blanks=data.get('blanks', [])
        )
        
        # Create answers if provided (for multiple-choice/true-false)
        answers = data.get('answers', [])
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
        
        serializer = DynamicFieldSerializer(question, model_name="questionbankquestion")
        
        return Response({
            "success": True,
            "data": serializer.data,
            "message": "Question created successfully."
        }, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def question_bank_question_detail_view(request, bank_id, question_id):
    """
    Retrieve, update, or delete a question from a question bank.
    """
    question_bank = get_object_or_404(QuestionBank, id=bank_id, teacher=request.user)
    question = get_object_or_404(QuestionBankQuestion, id=question_id, question_bank=question_bank)
    
    if request.method == 'GET':
        serializer = DynamicFieldSerializer(question, model_name="questionbankquestion")
        return Response({
            "success": True,
            "data": serializer.data,
            "message": "Question retrieved successfully."
        }, status=status.HTTP_200_OK)
    
    if request.method == 'PATCH':
        data = request.data
        
        # Update question fields
        for field in ['question_type', 'question_text', 'question_image', 'explanation', 'points', 'order', 'blanks']:
            if field in data:
                setattr(question, field, data[field])
        question.save()
        
        # Update answers if provided
        if 'answers' in data and isinstance(data['answers'], list):
            QuestionBankAnswer.objects.filter(question=question).delete()
            bulk_answers = []
            for idx, ans_data in enumerate(data['answers']):
                bulk_answers.append(QuestionBankAnswer(
                    question=question,
                    answer_text=ans_data.get('answer_text') or ans_data.get('text', ''),
                    answer_image=ans_data.get('answer_image'),
                    is_correct=bool(ans_data.get('is_correct', False)),
                    order=ans_data.get('order', idx)
                ))
            if bulk_answers:
                QuestionBankAnswer.objects.bulk_create(bulk_answers)
        
        serializer = DynamicFieldSerializer(question, model_name="questionbankquestion")
        
        return Response({
            "success": True,
            "data": serializer.data,
            "message": "Question updated successfully."
        }, status=status.HTTP_200_OK)
    
    if request.method == 'DELETE':
        question.delete()
        return Response({
            "success": True,
            "message": "Question deleted successfully."
        }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def export_questions_to_quiz_lesson_view(request, bank_id, lesson_id):
    """
    Export questions from a question bank to a quiz lesson.
    Expected payload: {
        "question_ids": [1, 2, 3]  // optional, if not provided exports all questions
    }
    """
    question_bank = get_object_or_404(QuestionBank, id=bank_id, teacher=request.user)
    lesson = get_object_or_404(Lesson, id=lesson_id)
    
    # Verify the lesson belongs to a course where the user is the instructor
    if lesson.course.instructor != request.user and not request.user.is_staff:
        return Response({
            "success": False,
            "message": "You are not authorized to export questions to this lesson."
        }, status=status.HTTP_403_FORBIDDEN)
    
    # Verify it's a quiz lesson
    if lesson.content_type != Lesson.ContentType.QUIZ:
        return Response({
            "success": False,
            "message": "This lesson is not a quiz lesson."
        }, status=status.HTTP_400_BAD_REQUEST)
    
    question_ids = request.data.get('question_ids', [])
    
    if question_ids:
        bank_questions = QuestionBankQuestion.objects.filter(
            id__in=question_ids,
            question_bank=question_bank
        )
    else:
        # Export all questions
        bank_questions = QuestionBankQuestion.objects.filter(question_bank=question_bank)
    
    if not bank_questions.exists():
        return Response({
            "success": False,
            "message": "No questions found to export."
        }, status=status.HTTP_404_NOT_FOUND)
    
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
    
    return Response({
        "success": True,
        "message": f"Successfully exported {exported_count} question(s) to quiz lesson.",
        "data": {
            "exported_count": exported_count,
            "lesson_id": lesson.id,
            "lesson_title": lesson.title
        }
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def export_questions_to_assessment_view(request, bank_id, course_id):
    """
    Export questions from a question bank to a final course assessment.
    Expected payload: {
        "question_ids": [1, 2, 3]  // optional, if not provided exports all questions
    }
    """
    question_bank = get_object_or_404(QuestionBank, id=bank_id, teacher=request.user)
    course = get_object_or_404(Course, id=course_id, instructor=request.user)
    
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
    
    question_ids = request.data.get('question_ids', [])
    
    if question_ids:
        bank_questions = QuestionBankQuestion.objects.filter(
            id__in=question_ids,
            question_bank=question_bank
        )
    else:
        # Export all questions
        bank_questions = QuestionBankQuestion.objects.filter(question_bank=question_bank)
    
    if not bank_questions.exists():
        return Response({
            "success": False,
            "message": "No questions found to export."
        }, status=status.HTTP_404_NOT_FOUND)
    
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
    
    return Response({
        "success": True,
        "message": f"Successfully exported {exported_count} question(s) to final assessment.",
        "data": {
            "exported_count": exported_count,
            "assessment_id": final_assessment.id,
            "assessment_title": final_assessment.title,
            "course_id": course.id
        }
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def import_questions_from_quiz_lesson_view(request, lesson_id, bank_id):
    """
    Import questions from a quiz lesson to a question bank.
    Expected payload: {
        "question_ids": [1, 2, 3]  // optional, if not provided imports all questions
    }
    """
    lesson = get_object_or_404(Lesson, id=lesson_id)
    question_bank = get_object_or_404(QuestionBank, id=bank_id, teacher=request.user)
    
    # Verify the lesson belongs to a course where the user is the instructor
    if lesson.course.instructor != request.user and not request.user.is_staff:
        return Response({
            "success": False,
            "message": "You are not authorized to import questions from this lesson."
        }, status=status.HTTP_403_FORBIDDEN)
    
    # Verify it's a quiz lesson
    if lesson.content_type != Lesson.ContentType.QUIZ:
        return Response({
            "success": False,
            "message": "This lesson is not a quiz lesson."
        }, status=status.HTTP_400_BAD_REQUEST)
    
    question_ids = request.data.get('question_ids', [])
    
    if question_ids:
        quiz_questions = QuizQuestion.objects.filter(id__in=question_ids, lesson=lesson)
    else:
        # Import all questions
        quiz_questions = QuizQuestion.objects.filter(lesson=lesson)
    
    if not quiz_questions.exists():
        return Response({
            "success": False,
            "message": "No questions found to import."
        }, status=status.HTTP_404_NOT_FOUND)
    
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
    
    return Response({
        "success": True,
        "message": f"Successfully imported {imported_count} question(s) to question bank.",
        "data": {
            "imported_count": imported_count,
            "question_bank_id": question_bank.id,
            "question_bank_name": question_bank.name,
            "lesson_id": lesson.id
        }
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def import_questions_from_assessment_view(request, course_id, bank_id):
    """
    Import questions from a final course assessment to a question bank.
    Expected payload: {
        "question_ids": [1, 2, 3]  // optional, if not provided imports all questions
    }
    """
    course = get_object_or_404(Course, id=course_id, instructor=request.user)
    question_bank = get_object_or_404(QuestionBank, id=bank_id, teacher=request.user)
    
    try:
        final_assessment = FinalCourseAssessment.objects.get(course=course)
    except FinalCourseAssessment.DoesNotExist:
        return Response({
            "success": False,
            "message": "Final assessment not found for this course."
        }, status=status.HTTP_404_NOT_FOUND)
    
    question_ids = request.data.get('question_ids', [])
    
    if question_ids:
        assessment_questions = AssessmentQuestion.objects.filter(
            id__in=question_ids,
            assessment=final_assessment
        )
    else:
        # Import all questions
        assessment_questions = AssessmentQuestion.objects.filter(assessment=final_assessment)
    
    if not assessment_questions.exists():
        return Response({
            "success": False,
            "message": "No questions found to import."
        }, status=status.HTTP_404_NOT_FOUND)
    
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
    
    return Response({
        "success": True,
        "message": f"Successfully imported {imported_count} question(s) to question bank.",
        "data": {
            "imported_count": imported_count,
            "question_bank_id": question_bank.id,
            "question_bank_name": question_bank.name,
            "assessment_id": final_assessment.id
        }
    }, status=status.HTTP_200_OK)

