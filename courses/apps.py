from django.apps import AppConfig


class CoursesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "courses"

    def ready(self):
        # Import signals
        try:
            import courses.signals  # noqa: F401
        except Exception:
            # Avoid crashing app if signals import fails in some contexts (e.g., migrations)
            pass