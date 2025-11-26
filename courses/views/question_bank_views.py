from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from courses.models import QuestionBank, QuestionBankQuestion, Course, Lesson, FinalCourseAssessment
from courses.serializers import DynamicFieldSerializer
from courses.services.pagination import paginate_queryset_or_list
from courses.services.question_bank_service import (
    get_question_banks,
    create_question_bank,
    get_question_bank,
    update_question_bank,
    delete_question_bank,
    get_question_bank_questions,
    create_question_bank_question,
    get_question_bank_question,
    update_question_bank_question,
    delete_question_bank_question,
    export_questions_to_quiz_lesson,
    export_questions_to_assessment,
    import_questions_from_quiz_lesson,
    import_questions_from_assessment,
)


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
        course_id = request.query_params.get('course_id')
        question_banks = get_question_banks(request.user, course_id=course_id)
        serializer = DynamicFieldSerializer(question_banks, many=True, model_name="questionbank")
        
        # Apply pagination
        return paginate_queryset_or_list(request, serializer.data)
    
    # POST: Create new question bank
    if request.method == 'POST':
        success, message, question_bank = create_question_bank(
            teacher=request.user,
            name=request.data.get('name'),
            description=request.data.get('description', ''),
            course_id=request.data.get('course_id'),
            is_active=request.data.get('is_active', True)
        )
        
        if not success:
            status_code = status.HTTP_400_BAD_REQUEST if "required" in message.lower() else status.HTTP_404_NOT_FOUND
            return Response({
                "success": False,
                "message": message
            }, status=status_code)
        
        serializer = DynamicFieldSerializer(question_bank, model_name="questionbank")
        
        return Response({
            "success": True,
            "data": serializer.data,
            "message": message
        }, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def question_bank_detail_view(request, bank_id):
    """
    Retrieve, update, or delete a question bank.
    """
    try:
        question_bank = get_question_bank(bank_id, request.user)
    except QuestionBank.DoesNotExist:
        return Response({
            "success": False,
            "message": "Question bank not found."
        }, status=status.HTTP_404_NOT_FOUND)
    
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
        success, message, updated_bank = update_question_bank(
            question_bank=question_bank,
            teacher=request.user,
            **request.data
        )
        
        if not success:
            return Response({
                "success": False,
                "message": message
            }, status=status.HTTP_404_NOT_FOUND)
        
        serializer = DynamicFieldSerializer(updated_bank, model_name="questionbank")
        
        return Response({
            "success": True,
            "data": serializer.data,
            "message": message
        }, status=status.HTTP_200_OK)
    
    if request.method == 'DELETE':
        try:
            success, message = delete_question_bank(bank_id, request.user)
            return Response({
                "success": True,
                "message": message
            }, status=status.HTTP_200_OK)
        except QuestionBank.DoesNotExist:
            return Response({
                "success": False,
                "message": "Question bank not found."
            }, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def question_bank_questions_list_create_view(request, bank_id):
    """
    List all questions in a question bank or create a new question.
    """
    try:
        question_bank = get_question_bank(bank_id, request.user)
    except QuestionBank.DoesNotExist:
        return Response({
            "success": False,
            "message": "Question bank not found."
        }, status=status.HTTP_404_NOT_FOUND)
    
    if request.method == 'GET':
        questions = get_question_bank_questions(question_bank)
        serializer = DynamicFieldSerializer(questions, many=True, model_name="questionbankquestion")
        
        # Apply pagination
        return paginate_queryset_or_list(request, serializer.data)
    
    # POST: Create new question
    if request.method == 'POST':
        question = create_question_bank_question(question_bank, request.data)
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
    try:
        question = get_question_bank_question(bank_id, question_id, request.user)
    except QuestionBank.DoesNotExist:
        return Response({
            "success": False,
            "message": "Question bank not found."
        }, status=status.HTTP_404_NOT_FOUND)
    except QuestionBankQuestion.DoesNotExist:
        return Response({
            "success": False,
            "message": "Question not found."
        }, status=status.HTTP_404_NOT_FOUND)
    
    if request.method == 'GET':
        serializer = DynamicFieldSerializer(question, model_name="questionbankquestion")
        return Response({
            "success": True,
            "data": serializer.data,
            "message": "Question retrieved successfully."
        }, status=status.HTTP_200_OK)
    
    if request.method == 'PATCH':
        updated_question = update_question_bank_question(question, request.data)
        serializer = DynamicFieldSerializer(updated_question, model_name="questionbankquestion")
        
        return Response({
            "success": True,
            "data": serializer.data,
            "message": "Question updated successfully."
        }, status=status.HTTP_200_OK)
    
    if request.method == 'DELETE':
        try:
            success, message = delete_question_bank_question(bank_id, question_id, request.user)
            return Response({
                "success": True,
                "message": message
            }, status=status.HTTP_200_OK)
        except (QuestionBank.DoesNotExist, QuestionBankQuestion.DoesNotExist):
            return Response({
                "success": False,
                "message": "Question bank or question not found."
            }, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def export_questions_to_quiz_lesson_view(request, bank_id, lesson_id):
    """
    Export questions from a question bank to a quiz lesson.
    Expected payload: {
        "question_ids": [1, 2, 3]  // optional, if not provided exports all questions
    }
    """
    try:
        question_bank = get_question_bank(bank_id, request.user)
    except QuestionBank.DoesNotExist:
        return Response({
            "success": False,
            "message": "Question bank not found."
        }, status=status.HTTP_404_NOT_FOUND)
    
    try:
        lesson = Lesson.objects.get(id=lesson_id)
    except Lesson.DoesNotExist:
        return Response({
            "success": False,
            "message": "Lesson not found."
        }, status=status.HTTP_404_NOT_FOUND)
    
    question_ids = request.data.get('question_ids', [])
    success, message, data = export_questions_to_quiz_lesson(
        question_bank=question_bank,
        lesson=lesson,
        teacher=request.user,
        question_ids=question_ids if question_ids else None
    )
    
    if not success:
        status_code = status.HTTP_400_BAD_REQUEST
        if "not authorized" in message.lower():
            status_code = status.HTTP_403_FORBIDDEN
        elif "not found" in message.lower():
            status_code = status.HTTP_404_NOT_FOUND
        
        return Response({
            "success": False,
            "message": message
        }, status=status_code)
    
    return Response({
        "success": True,
        "message": message,
        "data": data
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
    try:
        question_bank = get_question_bank(bank_id, request.user)
    except QuestionBank.DoesNotExist:
        return Response({
            "success": False,
            "message": "Question bank not found."
        }, status=status.HTTP_404_NOT_FOUND)
    
    try:
        course = Course.objects.get(id=course_id, instructor=request.user)
    except Course.DoesNotExist:
        return Response({
            "success": False,
            "message": "Course not found or you are not the instructor."
        }, status=status.HTTP_404_NOT_FOUND)
    
    question_ids = request.data.get('question_ids', [])
    success, message, data = export_questions_to_assessment(
        question_bank=question_bank,
        course=course,
        teacher=request.user,
        question_ids=question_ids if question_ids else None
    )
    
    if not success:
        status_code = status.HTTP_404_NOT_FOUND
        return Response({
            "success": False,
            "message": message
        }, status=status_code)
    
    return Response({
        "success": True,
        "message": message,
        "data": data
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
    try:
        question_bank = get_question_bank(bank_id, request.user)
    except QuestionBank.DoesNotExist:
        return Response({
            "success": False,
            "message": "Question bank not found."
        }, status=status.HTTP_404_NOT_FOUND)
    
    try:
        lesson = Lesson.objects.get(id=lesson_id)
    except Lesson.DoesNotExist:
        return Response({
            "success": False,
            "message": "Lesson not found."
        }, status=status.HTTP_404_NOT_FOUND)
    
    question_ids = request.data.get('question_ids', [])
    success, message, data = import_questions_from_quiz_lesson(
        question_bank=question_bank,
        lesson=lesson,
        teacher=request.user,
        question_ids=question_ids if question_ids else None
    )
    
    if not success:
        status_code = status.HTTP_400_BAD_REQUEST
        if "not authorized" in message.lower():
            status_code = status.HTTP_403_FORBIDDEN
        elif "not found" in message.lower():
            status_code = status.HTTP_404_NOT_FOUND
        
        return Response({
            "success": False,
            "message": message
        }, status=status_code)
    
    return Response({
        "success": True,
        "message": message,
        "data": data
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
    try:
        question_bank = get_question_bank(bank_id, request.user)
    except QuestionBank.DoesNotExist:
        return Response({
            "success": False,
            "message": "Question bank not found."
        }, status=status.HTTP_404_NOT_FOUND)
    
    try:
        course = Course.objects.get(id=course_id, instructor=request.user)
    except Course.DoesNotExist:
        return Response({
            "success": False,
            "message": "Course not found or you are not the instructor."
        }, status=status.HTTP_404_NOT_FOUND)
    
    question_ids = request.data.get('question_ids', [])
    success, message, data = import_questions_from_assessment(
        question_bank=question_bank,
        course=course,
        teacher=request.user,
        question_ids=question_ids if question_ids else None
    )
    
    if not success:
        status_code = status.HTTP_404_NOT_FOUND
        return Response({
            "success": False,
            "message": message
        }, status=status_code)
    
    return Response({
        "success": True,
        "message": message,
        "data": data
    }, status=status.HTTP_200_OK)
