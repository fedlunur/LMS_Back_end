# import os
# from django.core.wsgi import get_wsgi_application
# from whitenoise import WhiteNoise
# from pathlib import Path

# os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lms_project.settings')

# application = get_wsgi_application()
# BASE_DIR = Path(__file__).resolve().parent.parent
# application = WhiteNoise(application, root=str(BASE_DIR / "staticfiles"))




import os
from django.core.wsgi import get_wsgi_application
from whitenoise import WhiteNoise
from pathlib import Path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lms_project.settings')

application = get_wsgi_application()

BASE_DIR = Path(__file__).resolve().parent
application = WhiteNoise(application, root=str(BASE_DIR / "staticfiles"))
