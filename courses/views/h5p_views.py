"""
Views for H5P content integration.

Handles:
- Uploading and processing .h5p files
- Retrieving H5P content for frontend
- Linking H5P content to lessons
"""

import os
import json
import tempfile
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.http import JsonResponse, FileResponse, Http404
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from courses.models import H5PContent, H5PLibrary, Lesson, VideoLesson, QuizLesson, H5PResult
from courses.h5p_utils import process_h5p_file, get_h5p_core_files
from courses.serializers import (
    H5PContentSerializer, 
    H5PContentFrontendSerializer,
    H5PLibrarySerializer, 
    H5PResultSerializer
)



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_h5p_file_view(request):
    """
    Upload and process a .h5p file.
    
    Expected POST data:
    - h5p_file: The .h5p file to upload
    - title (optional): Custom title for the content
    - lesson_type (optional): 'video' or 'quiz' - type of lesson (inferred from lesson if not provided)
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

        if not lesson_id:
            return Response(
                {'error': 'lesson_id is mandatory'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Process the H5P file
        h5p_content = process_h5p_file(temp_path, title=title)
        
        # Link to lesson
        try:
            lesson = Lesson.objects.get(id=lesson_id)
            
            # Verify user has permission (must be instructor of the course)
            if lesson.course.instructor != request.user:
                return Response(
                    {'error': 'You do not have permission to modify this lesson'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Determine lesson type from lesson object if not provided
            if not lesson_type:
                lesson_type = lesson.content_type

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
        
        # Serialize and return - use frontend serializer for cleaner response
        serializer = H5PContentFrontendSerializer(h5p_content, context={'request': request})
        return Response({
            'success': True,
            'content': serializer.data,
            'lesson_id': lesson_id,
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
        data = serializer.data
        
        # Explicitly add lesson_id if not present in serializer data
        if 'lesson_id' not in data:
            lesson_id = None
            # Check video lessons
            video_lesson = h5p_content.video_lessons.first()
            if video_lesson:
                lesson_id = video_lesson.lesson.id
            else:
                # Check quiz lessons
                quiz_lesson = h5p_content.quiz_lessons.first()
                if quiz_lesson:
                    lesson_id = quiz_lesson.lesson.id
            data['lesson_id'] = lesson_id
            
        return Response(data, status=status.HTTP_200_OK)
    
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
        
        # Use frontend-optimized serializer
        serializer = H5PContentFrontendSerializer(h5p_content, context={'request': request})
        data = serializer.data
        # Explicitly set lesson_id from the request parameter
        data['lesson_id'] = int(lesson_id)
        return Response(data, status=status.HTTP_200_OK)
    
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
        
        # Use frontend serializer for cleaner response
        serializer = H5PContentFrontendSerializer(h5p_content, context={'request': request})
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
    
    # Use frontend serializer for list view as well
    serializer = H5PContentFrontendSerializer(contents, many=True, context={'request': request})
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def save_h5p_result_view(request):
    """
    Save results from H5P content execution.
    
    Expected POST data:
    - content_id: ID of the H5P content
    - score: Score achieved
    - max_score: Maximum possible score
    - time: Time spent in seconds
    - result_json: Detailed result object (optional)
    """
    content_id = request.data.get('content_id')
    score = request.data.get('score')
    max_score = request.data.get('max_score')
    
    if not content_id or score is None or max_score is None:
        return Response(
            {'error': 'content_id, score, and max_score are required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        h5p_content = H5PContent.objects.get(id=content_id)
        
        # Try to find the lesson context
        # This is tricky because one H5P content could be used in multiple lessons
        # Ideally, the frontend should send the lesson_id if known
        lesson_id = request.data.get('lesson_id')
        lesson = None
        
        if lesson_id:
            try:
                lesson = Lesson.objects.get(id=lesson_id)
            except Lesson.DoesNotExist:
                pass
        
        # Create result record
        result = H5PResult.objects.create(
            student=request.user,
            h5p_content=h5p_content,
            lesson=lesson,
            score=float(score),
            max_score=float(max_score),
            time=int(request.data.get('time', 0)),
            result_json=request.data.get('result_json')
        )
        
        serializer = H5PResultSerializer(result)
        return Response({
            'success': True,
            'result': serializer.data
        }, status=status.HTTP_201_CREATED)
        
    except H5PContent.DoesNotExist:
        return Response(
            {'error': 'H5P content not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': f'Error saving result: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_h5p_content_json_view(request, content_id):
    """
    Serve content.json for H5P content.
    This is required for H5P rendering in React.
    
    Returns the content.json file as JSON response.
    """
    try:
        h5p_content = H5PContent.objects.get(id=content_id)
        
        # Check access permissions (similar to get_h5p_content_view)
        # For now, allow if user is authenticated
        
        # Build path to content.json
        content_json_path = os.path.join(
            settings.MEDIA_ROOT,
            'h5p',
            'content',
            str(h5p_content.id),
            'content.json'
        )
        
        if not os.path.exists(content_json_path):
            return Response(
                {'error': 'content.json not found for this H5P content'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Read and return JSON
        with open(content_json_path, 'r', encoding='utf-8') as f:
            content_data = json.load(f)
        
        # Return as JSON response with proper headers
        response = JsonResponse(content_data, json_dumps_params={'ensure_ascii': False})
        response['Access-Control-Allow-Origin'] = '*'  # Adjust for production
        response['Content-Type'] = 'application/json; charset=utf-8'
        return response
    
    except H5PContent.DoesNotExist:
        return Response(
            {'error': 'H5P content not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': f'Error reading content.json: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_h5p_library_file_view(request, library_id, file_path):
    """
    Serve library files for H5P rendering.
    
    Args:
        library_id: ID of the H5PLibrary
        file_path: Relative path to the file within the library (e.g., 'js/quiz.js')
    
    Returns the library file with appropriate content type.
    """
    try:
        library = H5PLibrary.objects.get(id=library_id)
        
        # Build file path
        if library.library_path:
            library_base_path = os.path.join(settings.MEDIA_ROOT, library.library_path)
        else:
            library_base_path = os.path.join(
                settings.MEDIA_ROOT,
                'h5p',
                'libraries',
                f"{library.name}-{library.major_version}.{library.minor_version}.{library.patch_version}"
            )
        
        # Sanitize file_path to prevent directory traversal
        file_path = file_path.lstrip('/')
        if '..' in file_path or file_path.startswith('/'):
            return Response(
                {'error': 'Invalid file path'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        full_file_path = os.path.join(library_base_path, file_path)
        
        # Ensure the file is within the library directory
        if not os.path.abspath(full_file_path).startswith(os.path.abspath(library_base_path)):
            return Response(
                {'error': 'Invalid file path'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not os.path.exists(full_file_path) or not os.path.isfile(full_file_path):
            return Response(
                {'error': 'Library file not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Determine content type
        ext = os.path.splitext(file_path)[1].lower()
        content_types = {
            '.js': 'application/javascript',
            '.css': 'text/css',
            '.json': 'application/json',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.svg': 'image/svg+xml',
            '.woff': 'font/woff',
            '.woff2': 'font/woff2',
            '.ttf': 'font/ttf',
            '.eot': 'application/vnd.ms-fontobject',
        }
        content_type = content_types.get(ext, 'application/octet-stream')
        
        # Serve file
        response = FileResponse(open(full_file_path, 'rb'), content_type=content_type)
        response['Access-Control-Allow-Origin'] = '*'  # Adjust for production
        return response
    
    except H5PLibrary.DoesNotExist:
        return Response(
            {'error': 'H5P library not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': f'Error serving library file: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_h5p_content_file_view(request, content_id, file_path):
    """
    Serve content files (images, videos, etc.) for H5P rendering.
    
    Args:
        content_id: ID of the H5PContent
        file_path: Relative path to the file within the content directory
    """
    try:
        h5p_content = H5PContent.objects.get(id=content_id)
        
        # Build file path
        content_base_path = os.path.join(
            settings.MEDIA_ROOT,
            'h5p',
            'content',
            str(h5p_content.id)
        )
        
        # Sanitize file_path to prevent directory traversal
        file_path = file_path.lstrip('/')
        if '..' in file_path or file_path.startswith('/'):
            return Response(
                {'error': 'Invalid file path'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        full_file_path = os.path.join(content_base_path, file_path)
        
        # Ensure the file is within the content directory
        if not os.path.abspath(full_file_path).startswith(os.path.abspath(content_base_path)):
            return Response(
                {'error': 'Invalid file path'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not os.path.exists(full_file_path) or not os.path.isfile(full_file_path):
            return Response(
                {'error': 'Content file not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Determine content type
        ext = os.path.splitext(file_path)[1].lower()
        content_types = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.svg': 'image/svg+xml',
            '.webp': 'image/webp',
            '.mp4': 'video/mp4',
            '.webm': 'video/webm',
            '.ogg': 'video/ogg',
            '.mp3': 'audio/mpeg',
            '.wav': 'audio/wav',
        }
        content_type = content_types.get(ext, 'application/octet-stream')
        
        # Serve file
        response = FileResponse(open(full_file_path, 'rb'), content_type=content_type)
        response['Access-Control-Allow-Origin'] = '*'  # Adjust for production
        return response
    
    except H5PContent.DoesNotExist:
        return Response(
            {'error': 'H5P content not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': f'Error serving content file: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_h5p_core_files_view(request):
    """
    Get H5P core file URLs.
    
    Returns URLs for H5P core JavaScript and CSS files that must be loaded
    before rendering any H5P content.
    """
    core_files = get_h5p_core_files(request)
    return Response(core_files, status=status.HTTP_200_OK)

