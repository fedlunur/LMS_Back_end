from ..models import Enrollment, Lesson, LessonProgress, Module, ModuleProgress
from .access_service import is_lesson_accessible

def mark_lesson_completed(user, lesson_id):
    """
    Mark a lesson as completed for the user.
    Updates lesson progress and cascades to enrollment and module progress.
    Also unlocks next lesson if available.
    """
    try:
        lesson = Lesson.objects.get(id=lesson_id)
        enrollment = Enrollment.objects.get(student=user, course=lesson.course)
        
        if enrollment.payment_status != 'completed':
            return False, "Payment not completed for this course."
        
        # Check if lesson is accessible
        if not is_lesson_accessible(user, lesson):
            return False, "Lesson is not accessible yet."
        
        # Get or create lesson progress
        progress, created = LessonProgress.objects.get_or_create(
            enrollment=enrollment,
            lesson=lesson,
            defaults={'progress': 0.0}
        )
        
        # Mark as completed
        progress.mark_completed(100.0)
        
        # Update module progress if lesson has a module
        if lesson.module:
            module_progress, _ = ModuleProgress.objects.get_or_create(
                enrollment=enrollment,
                module=lesson.module
            )
            module_progress.calculate_progress()
            
            # If module is completed, unlock next module
            if module_progress.completed:
                next_module = Module.objects.filter(
                    course=lesson.course,
                    order__gt=lesson.module.order
                ).order_by('order').first()
                
                if next_module:
                    ModuleProgress.objects.get_or_create(
                        enrollment=enrollment,
                        module=next_module,
                        defaults={'progress': 0.0, 'completed': False}
                    )
        
        # Determine next lesson to unlock info
        next_lesson = None
        if lesson.module:
            # Next lesson in same module
            next_lesson = Lesson.objects.filter(
                module=lesson.module,
                order__gt=lesson.order
            ).order_by('order').first()
            # If none, first lesson of next module
            if not next_lesson:
                next_module = Module.objects.filter(
                    course=lesson.course,
                    order__gt=lesson.module.order
                ).order_by('order').first()
                if next_module:
                    next_lesson = Lesson.objects.filter(module=next_module).order_by('order').first()
        else:
            # Lessons without module: next by order within course
            next_lesson = Lesson.objects.filter(
                course=lesson.course,
                module__isnull=True,
                order__gt=lesson.order
            ).order_by('order').first()

        return True, "Lesson marked as completed successfully.", (next_lesson.id if next_lesson else None)
    
    except Lesson.DoesNotExist:
        return False, "Lesson not found."
    except Enrollment.DoesNotExist:
        return False, "You are not enrolled in this course."
