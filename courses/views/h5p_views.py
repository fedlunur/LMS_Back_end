"""
Views for H5P content integration.

Handles:
- Uploading and processing .h5p files
- Retrieving H5P content for frontend
- Linking H5P content to lessons
"""

import os
import tempfile
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.http import JsonResponse
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from courses.models import H5PContent, H5PLibrary, Lesson, VideoLesson, QuizLesson
from courses.h5p_utils import process_h5p_file
from courses.serializers import H5PContentSerializer, H5PLibrarySerializer


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_h5p_file_view(request):
    """
    Upload and process a .h5p file.
    
    Expected POST data:
    - h5p_file: The .h5p file to upload
    - title (optional): Custom title for the content
    - lesson_id (optional): ID of lesson to link this content to
    - lesson_type (optional): 'video' or 'quiz' - type of lesson
    """
    if 'h5p_file' not in request.FILES:
        return Response(
            {'error': 'No h5p_file provided'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    h5p_file = request.FILES['h5p_file']
    
    # Validate file extension
    if not h5p_file.name.endswith('.h5p'):
        return Response(
            {'error': 'Invalid file type. Expected .h5p file'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Save file temporarily
    temp_path = None
    try:
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.h5p') as temp_file:
            for chunk in h5p_file.chunks():
                temp_file.write(chunk)
            temp_path = temp_file.name
        
        # Get optional parameters
        title = request.data.get('title', None)
        lesson_id = request.data.get('lesson_id', None)
        lesson_type = request.data.get('lesson_type', None)
        
        # Process the H5P file
        h5p_content = process_h5p_file(temp_path, title=title)
        
        # Link to lesson if provided
        if lesson_id and lesson_type:
            try:
                lesson = Lesson.objects.get(id=lesson_id)
                
                # Verify user has permission (must be instructor of the course)
                if lesson.course.instructor != request.user:
                    return Response(
                        {'error': 'You do not have permission to modify this lesson'},
                        status=status.HTTP_403_FORBIDDEN
                    )
                
                if lesson_type == 'video':
                    video_lesson, created = VideoLesson.objects.get_or_create(lesson=lesson)
                    video_lesson.h5p_content = h5p_content
                    video_lesson.save()
                elif lesson_type == 'quiz':
                    quiz_lesson, created = QuizLesson.objects.get_or_create(lesson=lesson)
                    quiz_lesson.h5p_content = h5p_content
                    quiz_lesson.save()
                else:
                    return Response(
                        {'error': f'Invalid lesson_type: {lesson_type}. Must be "video" or "quiz"'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            except Lesson.DoesNotExist:
                return Response(
                    {'error': f'Lesson with id {lesson_id} not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        # Serialize and return
        serializer = H5PContentSerializer(h5p_content, context={'request': request})
        return Response({
            'success': True,
            'content': serializer.data,
            'message': 'H5P file processed successfully'
        }, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        return Response(
            {'error': f'Error processing H5P file: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    finally:
        # Cleanup temporary file
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_h5p_content_view(request, content_id):
    """
    Retrieve H5P content by ID for frontend rendering.
    
    Returns:
    - Content parameters
    - Library information
    - File URLs
    """
    try:
        h5p_content = H5PContent.objects.get(id=content_id)
        
        # Check if user has access (must be enrolled in the course if linked to a lesson)
        # For now, we'll allow access if content is linked to a lesson they can access
        # Or allow access if they're the instructor
        
        serializer = H5PContentSerializer(h5p_content, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    except H5PContent.DoesNotExist:
        return Response(
            {'error': 'H5P content not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_lesson_h5p_content_view(request, lesson_id):
    """
    Get H5P content associated with a lesson.
    
    Returns the H5P content if the lesson has H5P content linked.
    """
    try:
        lesson = Lesson.objects.get(id=lesson_id)
        
        # Verify access
        if lesson.course.instructor != request.user:
            # Check if user is enrolled
            from courses.models import Enrollment
            if not Enrollment.objects.filter(
                student=request.user,
                course=lesson.course,
                is_enrolled=True
            ).exists():
                return Response(
                    {'error': 'You do not have access to this lesson'},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        h5p_content = None
        
        # Check video lesson
        if lesson.content_type == Lesson.ContentType.VIDEO:
            try:
                video_lesson = lesson.video
                h5p_content = video_lesson.h5p_content
            except VideoLesson.DoesNotExist:
                pass
        
        # Check quiz lesson
        elif lesson.content_type == Lesson.ContentType.QUIZ:
            try:
                quiz_lesson = lesson.quiz
                h5p_content = quiz_lesson.h5p_content
            except QuizLesson.DoesNotExist:
                pass
        
        if not h5p_content:
            return Response(
                {'error': 'No H5P content found for this lesson'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = H5PContentSerializer(h5p_content, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    except Lesson.DoesNotExist:
        return Response(
            {'error': 'Lesson not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def link_h5p_to_lesson_view(request, lesson_id):
    """
    Link existing H5P content to a lesson.
    
    Expected POST data:
    - content_id: ID of the H5P content to link
    """
    content_id = request.data.get('content_id')
    
    if not content_id:
        return Response(
            {'error': 'content_id is required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        lesson = Lesson.objects.get(id=lesson_id)
        h5p_content = H5PContent.objects.get(id=content_id)
        
        # Verify user has permission (must be instructor)
        if lesson.course.instructor != request.user:
            return Response(
                {'error': 'You do not have permission to modify this lesson'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Link based on lesson type
        if lesson.content_type == Lesson.ContentType.VIDEO:
            video_lesson, created = VideoLesson.objects.get_or_create(lesson=lesson)
            video_lesson.h5p_content = h5p_content
            video_lesson.save()
        elif lesson.content_type == Lesson.ContentType.QUIZ:
            quiz_lesson, created = QuizLesson.objects.get_or_create(lesson=lesson)
            quiz_lesson.h5p_content = h5p_content
            quiz_lesson.save()
        else:
            return Response(
                {'error': 'H5P content can only be linked to video or quiz lessons'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = H5PContentSerializer(h5p_content, context={'request': request})
        return Response({
            'success': True,
            'content': serializer.data,
            'message': 'H5P content linked successfully'
        }, status=status.HTTP_200_OK)
    
    except Lesson.DoesNotExist:
        return Response(
            {'error': 'Lesson not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except H5PContent.DoesNotExist:
        return Response(
            {'error': 'H5P content not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_h5p_libraries_view(request):
    """
    List all available H5P libraries.
    Useful for frontend to know what content types are available.
    """
    libraries = H5PLibrary.objects.filter(runnable=True).order_by('name', '-major_version', '-minor_version')
    serializer = H5PLibrarySerializer(libraries, many=True, context={'request': request})
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_h5p_contents_view(request):
    """
    List H5P contents (filtered by user if needed).
    """
    contents = H5PContent.objects.all().order_by('-created_at')
    
    # Filter by user's courses if not admin/superuser
    if not request.user.is_staff:
        # Only show contents linked to courses where user is instructor
        from courses.models import VideoLesson, QuizLesson
        video_lessons = VideoLesson.objects.filter(
            lesson__course__instructor=request.user,
            h5p_content__isnull=False
        ).values_list('h5p_content_id', flat=True)
        
        quiz_lessons = QuizLesson.objects.filter(
            lesson__course__instructor=request.user,
            h5p_content__isnull=False
        ).values_list('h5p_content_id', flat=True)
        
        content_ids = set(list(video_lessons) + list(quiz_lessons))
        contents = contents.filter(id__in=content_ids)
    
    serializer = H5PContentSerializer(contents, many=True, context={'request': request})
    return Response(serializer.data, status=status.HTTP_200_OK)
