from courses.models import Enrollment, Lesson, Module, LessonProgress

def is_module_accessible(user, module):
    """
    Check if a module is accessible for the given user.
    A module is accessible if:
    - User is enrolled in the course
    - It's the first module, or all lessons in the previous module are completed
    """
    if not user.is_authenticated:
        return False
    
    try:
        enrollment = Enrollment.objects.get(student=user, course=module.course)
    except Enrollment.DoesNotExist:
        return False
    
    # Check payment status
    if enrollment.payment_status != 'completed':
        return False
    
    # First module is always accessible
    first_module = Module.objects.filter(course=module.course).order_by('order').first()
    if module == first_module:
        return True
    
    # Find previous module
    previous_module = Module.objects.filter(
        course=module.course,
        order__lt=module.order
    ).order_by('-order').first()
    
    if not previous_module:
        return True  # Safeguard
    
    # Check if all lessons in previous module are completed
    previous_lessons = Lesson.objects.filter(module=previous_module)
    if not previous_lessons.exists():
        return True  # Empty module, allow access
    
    for lesson in previous_lessons:
        try:
            progress = LessonProgress.objects.get(enrollment=enrollment, lesson=lesson)
            if not progress.completed:
                return False
        except LessonProgress.DoesNotExist:
            return False
    return True

def is_lesson_accessible(user, lesson):
    """
    Check if a lesson is accessible for the given user.
    A lesson is accessible if:
    - User is enrolled in the course
    - Module containing the lesson is accessible
    - It's the first lesson in the module, or the previous lesson in the same module is completed
    """
    if not user.is_authenticated:
        return False
    
    try:
        enrollment = Enrollment.objects.get(student=user, course=lesson.course)
    except Enrollment.DoesNotExist:
        return False
    
    # Check payment status
    if enrollment.payment_status != 'completed':
        return False
    
    # If lesson has a module, check if module is accessible
    if lesson.module:
        if not is_module_accessible(user, lesson.module):
            return False
        
        # First lesson in module is always accessible
        first_lesson_in_module = Lesson.objects.filter(
            module=lesson.module
        ).order_by('order').first()
        
        if lesson == first_lesson_in_module:
            return True
        
        # Find previous lesson in the same module
        previous_lesson = Lesson.objects.filter(
            module=lesson.module,
            order__lt=lesson.order
        ).order_by('-order').first()
        
        if not previous_lesson:
            return True  # Safeguard
        
        # Check if previous lesson is completed
        try:
            progress = LessonProgress.objects.get(enrollment=enrollment, lesson=previous_lesson)
            return progress.completed
        except LessonProgress.DoesNotExist:
            return False
    else:
        # Lesson without module - check course-level ordering
        first_lesson = Lesson.objects.filter(
            course=lesson.course,
            module__isnull=True
        ).order_by('order').first()
        
        if lesson == first_lesson:
            return True
        
        # Find previous lesson without module
        previous_lesson = Lesson.objects.filter(
            course=lesson.course,
            module__isnull=True,
            order__lt=lesson.order
        ).order_by('-order').first()
        
        if not previous_lesson:
            return True
        
        try:
            progress = LessonProgress.objects.get(enrollment=enrollment, lesson=previous_lesson)
            return progress.completed
        except LessonProgress.DoesNotExist:
            return False
