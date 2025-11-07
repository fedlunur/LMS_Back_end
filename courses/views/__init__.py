from .base import GenericModelViewSet
from .course_views import *
from .lesson_views import *
from .quiz_views import *
from .assignment_views import *
from .assessment_views import *
from .progress_views import *
from .instructor_views import *
from .student_views import *
from .content_views import *
from .rating_views import *
from .certificate_views import *

__all__ = [
    'GenericModelViewSet',
    # Export all view functions/classes as needed
]