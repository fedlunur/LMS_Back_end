from django.apps import apps
from django.db.models import ForeignKey, ManyToOneRel, FileField, ImageField
from rest_framework import serializers
from user_managment.models import User
from user_managment.serializers import UserDetailSerializer
from django.conf import settings

# Import your attachment models
from courses.models import *  # Add more if needed
from courses.h5p_utils import get_h5p_library_url, get_h5p_content_url, get_h5p_core_files

# ----------------- WRITABLE NESTED FIELD -----------------
class WritableNestedField(serializers.PrimaryKeyRelatedField):
    def __init__(self, nested_serializer_class, **kwargs):
        self.nested_serializer_class = nested_serializer_class
        super().__init__(**kwargs)

    def get_choices(self, cutoff=None):
        queryset = self.get_queryset()
        if queryset is None:
            return {}
        return {item.pk: str(item) for item in queryset}

    def to_representation(self, value):
        if getattr(value, "_state", None) is None:
            value = self.get_queryset().get(pk=value.pk)
        request = self.context.get("request")
        if request and request.accepted_renderer.format == "html":
            return value.pk
        return self.nested_serializer_class(value, context=self.context).data


# ----------------- UTILITY TO NORMALIZE MODEL NAMES -----------------
def normalize_model_name(name: str) -> str:
    """Remove underscores and lowercase to match model_mapping keys"""
    return name.replace("_", "").lower()


# ----------------- GET ALL MODELS IN COURSES APP -----------------
all_models = apps.get_app_config('courses').get_models()
model_mapping = {model.__name__.lower(): model for model in all_models}

# ----------------- LESSON TYPES WITH ATTACHMENTS -----------------
LESSON_TYPES_WITH_ATTACHMENTS = ["VideoLesson", "ArticleLesson", "QuizLesson", "AssignmentLesson"]


# ----------------- DYNAMIC FIELD SERIALIZER -----------------
class DynamicFieldSerializer(serializers.ModelSerializer):
    class Meta:
        model = None
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        model_name = kwargs.pop("model_name", None)
        if not model_name:
            super().__init__(*args, **kwargs)
            return

        normalized_name = normalize_model_name(model_name)
        model = model_mapping.get(normalized_name)
        if not model:
            raise ValueError(f"Invalid model name: {model_name} (normalized: {normalized_name})")

        self.Meta.model = model
        self.Meta.fields = "__all__"
        super().__init__(*args, **kwargs)

        # ----------------- ADD WRITABLE ATTACHMENTS FIELD -----------------
        # For models that support attachments, add a writable field to accept file uploads
        # We do this ONLY if we are processing input data (write mode)
        # Otherwise (read mode), we let the loop below handle it as a nested serializer
        if hasattr(self, 'initial_data') and model.__name__ in LESSON_TYPES_WITH_ATTACHMENTS:
            self.fields["attachments"] = serializers.ListField(
                child=serializers.FileField(),
                required=False,
                write_only=True
            )

        # ----------------- ADD MODEL PROPERTIES AS READ-ONLY -----------------
        for attr_name in dir(model):
            attr = getattr(model, attr_name, None)
            if isinstance(attr, property):
                # Avoid serializing heavy/complex properties that yield QuerySets or models
                # The video player has a dedicated endpoint; do not expose checkpoint_quizzes here
                if model.__name__ == "VideoLesson" and attr_name == "checkpoint_quizzes":
                    continue
                self.fields[attr_name] = serializers.ReadOnlyField()

        # ----------------- HANDLE FOREIGN KEYS -----------------
        for f in model._meta.get_fields():
            if isinstance(f, ForeignKey):
                is_optional = getattr(f, "null", False) or getattr(f, "blank", False)
                self.fields[f.name] = serializers.PrimaryKeyRelatedField(
                    queryset=f.related_model.objects.all(),
                    required=not is_optional,
                    allow_null=is_optional
                )

        # ----------------- HANDLE ATTACHMENTS, EXTERNAL LINKS & QUIZ ANSWERS -----------------
        for f in model._meta.get_fields():
            if isinstance(f, ManyToOneRel):
                related_model = f.related_model
                related_name = f.get_accessor_name()

                # Attachments
                if "attachment" in related_model.__name__.lower() or f.name == "attachments":
                    # Skip if we are in write mode and have already defined a writable attachments field
                    if related_name == "attachments" and hasattr(self, 'initial_data') and model.__name__ in LESSON_TYPES_WITH_ATTACHMENTS:
                        continue

                    class AttachmentSerializer(serializers.ModelSerializer):
                        class Meta:
                            model = related_model
                            fields = ["id", "file", "uploaded_at"] if hasattr(related_model, "file") else "__all__"
                        
                        def to_representation(self, instance):
                            data = super().to_representation(instance)
                            # Convert file URLs to /media/... format
                            if "file" in data and data["file"]:
                                file_url = data["file"]
                                if isinstance(file_url, str):
                                    # Extract /media/... path from full URL
                                    if file_url.startswith("http"):
                                        # Full URL like http://localhost:8888/media/...
                                        if "/media/" in file_url:
                                            media_index = file_url.find("/media/")
                                            data["file"] = file_url[media_index:]
                                        else:
                                            # Just use the path part
                                            from urllib.parse import urlparse
                                            parsed = urlparse(file_url)
                                            data["file"] = parsed.path if parsed.path else f"/media/{file_url}"
                                    elif not file_url.startswith("/media/"):
                                        # Relative path without /media/
                                        data["file"] = f"/media/{file_url.lstrip('/')}"
                                    # If already starts with /media/, keep it as is
                            return data
                    
                    self.fields[related_name] = AttachmentSerializer(many=True, read_only=True)
                    continue

                # External links
                elif "externallink" in related_model.__name__.lower() or f.name == "external_links_items":
                    class ExternalLinkSerializer(serializers.ModelSerializer):
                        class Meta:
                            model = related_model
                            fields = ["id", "title", "url", "description"]
                    self.fields[related_name] = ExternalLinkSerializer(many=True, read_only=True)
                    continue

                # Quiz answers
                elif related_model.__name__ == "QuizAnswer" and model.__name__ == "QuizQuestion":
                    class QuizAnswerSerializer(serializers.ModelSerializer):
                        class Meta:
                            model = related_model
                            fields = ["id", "answer_text", "answer_image", "is_correct", "order"]
                    self.fields[related_name] = QuizAnswerSerializer(many=True, read_only=True)
                    continue
                
                # Question bank answers
                elif related_model.__name__ == "QuestionBankAnswer" and model.__name__ == "QuestionBankQuestion":
                    class QuestionBankAnswerSerializer(serializers.ModelSerializer):
                        class Meta:
                            model = related_model
                            fields = ["id", "answer_text", "answer_image", "is_correct", "order"]
                    self.fields[related_name] = QuestionBankAnswerSerializer(many=True, read_only=True)
                    continue

        # ----------------- INPUT ALIASES FOR FRONTEND COMPAT -----------------
        # Allow creating QuizQuestion with 'type' and 'question' aliases
        if self.Meta.model.__name__ == "QuizQuestion":
            self.fields.setdefault("type", serializers.CharField(source="question_type", required=False))
            self.fields.setdefault("question", serializers.CharField(source="question_text", required=False))
        # Allow creating QuizAnswer with 'text' alias
        if self.Meta.model.__name__ == "QuizAnswer":
            self.fields.setdefault("text", serializers.CharField(source="answer_text", required=False))
        # Allow creating QuestionBankQuestion with 'type' and 'question' aliases
        if self.Meta.model.__name__ == "QuestionBankQuestion":
            self.fields.setdefault("type", serializers.CharField(source="question_type", required=False))
            self.fields.setdefault("question", serializers.CharField(source="question_text", required=False))
        # Allow creating QuestionBankAnswer with 'text' alias
        if self.Meta.model.__name__ == "QuestionBankAnswer":
            self.fields.setdefault("text", serializers.CharField(source="answer_text", required=False))

    # ----------------- CUSTOM REPRESENTATION (CLEAN OUTPUT) -----------------
    def to_representation(self, instance):
        data = super().to_representation(instance)
        model = instance.__class__

        # Convert file field URLs to /media/... format (applies to all file fields dynamically)
        for field in model._meta.get_fields():
            if isinstance(field, (FileField, ImageField)):
                field_name = field.name
                if field_name in data and data[field_name]:
                    file_url = data[field_name]
                    if isinstance(file_url, str):
                        # Extract /media/... path from full URL
                        if file_url.startswith("http"):
                            # Full URL like http://localhost:8888/media/...
                            if "/media/" in file_url:
                                media_index = file_url.find("/media/")
                                data[field_name] = file_url[media_index:]
                            else:
                                # Just use the path part
                                from urllib.parse import urlparse
                                parsed = urlparse(file_url)
                                data[field_name] = parsed.path if parsed.path else f"/media/{file_url}"
                        elif not file_url.startswith("/media/"):
                            # Relative path without /media/
                            data[field_name] = f"/media/{file_url.lstrip('/')}"
                        # If already starts with /media/, keep it as is

        # Hide checkpoint quiz correct answers from non-staff
        if instance.__class__.__name__ == "VideoCheckpointQuiz":
            request = self.context.get("request") if hasattr(self, "context") else None
            is_staff = bool(getattr(getattr(request, "user", None), "is_staff", False)) if request else False
            if not is_staff:
                data.pop("correct_answer_index", None)
            return data

        # If not a quiz question, return default
        if instance.__class__.__name__ != "QuizQuestion":
            return data

        # Remove unwanted fields
        for field in ["lesson", "quiz_lesson", "pk", "created_at", "updated_at", "blanks_count", "total_marks"]:
            data.pop(field, None)

        question_type = data.get("question_type")
        base = {
            "id": data.get("id"),
            "type": question_type,
            "question": data.get("question_text"),
            "image": data.get("question_image"),
            "points": data.get("points"),
            "explanation": data.get("explanation"),
        }

        # Render per question type
        if question_type == "multiple-choice":
            base["answers"] = [
                {"id": a["id"], "text": a["answer_text"]}
                for a in data.get("answers", [])
            ]

        elif question_type == "true-false":
            base["answers"] = [
                {"id": a["id"], "text": a["answer_text"]}
                for a in data.get("answers", [])
            ]

        elif question_type == "fill-blank":
            base["blanks"] = [
                {"id": a["id"], "correct_answer": a["answer_text"]}
                for a in data.get("answers", [])
                if a.get("is_correct", True)
            ]

        else:
            base["answers"] = data.get("answers", [])

        return base

    # ----------------- CREATE -----------------
    def create(self, validated_data):
        model = self.Meta.model
        attachments = validated_data.pop("attachments", None)
        lesson_instance = validated_data.pop("lesson", None)

        # Ensure single config per lesson and friendly validation
        if model.__name__ == "QuizConfiguration":
            from rest_framework.exceptions import ValidationError
            if not lesson_instance:
                # Explicit error instead of bubbling up DB IntegrityError
                raise ValidationError({"lesson": "This field is required."})
            obj, _ = model.objects.update_or_create(
                lesson=lesson_instance,
                defaults=validated_data
            )
            return obj

        if lesson_instance and model.__name__ in LESSON_TYPES_WITH_ATTACHMENTS:
            obj, created = model.objects.update_or_create(
                lesson=lesson_instance,
                defaults=validated_data
            )
            if attachments and hasattr(obj, "attachments"):
                obj.attachments.all().delete()
                # Find the correct FK field name in attachment model
                attachment_model = obj._meta.get_field("attachments").related_model
                fk_field_name = None
                for field in attachment_model._meta.get_fields():
                    if isinstance(field, ForeignKey) and field.related_model == model:
                        fk_field_name = field.name
                        break
                if fk_field_name:
                    for f in attachments:
                        attachment_model.objects.create(**{fk_field_name: obj, "file": f})
            return obj

        # For other models that still require 'lesson' FK (e.g., QuizQuestion), put it back
        if lesson_instance is not None and any(f.name == "lesson" for f in model._meta.get_fields()):
            validated_data["lesson"] = lesson_instance

        # Graceful idempotency for VideoCheckpointResponse: update existing instead of erroring
        if model.__name__ == "VideoCheckpointResponse":
            student = validated_data.get("student")
            checkpoint_quiz = validated_data.get("checkpoint_quiz")
            if checkpoint_quiz and not validated_data.get("lesson"):
                try:
                    validated_data["lesson"] = checkpoint_quiz.lesson
                except Exception:
                    pass
            if student and checkpoint_quiz:
                obj, _ = model.objects.update_or_create(
                    student=student,
                    checkpoint_quiz=checkpoint_quiz,
                    defaults=validated_data
                )
                return obj

        return super().create(validated_data)

    # ----------------- UPDATE -----------------
    def update(self, instance, validated_data):
        model = self.Meta.model
        attachments = validated_data.pop("attachments", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if attachments and hasattr(instance, "attachments"):
            instance.attachments.all().delete()
            attachment_model = instance._meta.get_field("attachments").related_model
            fk_field_name = None
            for field in attachment_model._meta.get_fields():
                if isinstance(field, ForeignKey) and field.related_model == model:
                    fk_field_name = field.name
                    break
            if fk_field_name:
                for f in attachments:
                    attachment_model.objects.create(**{fk_field_name: instance, "file": f})

        return instance


# ---------------------------------------------------------------------------
# H5P Serializers
# ---------------------------------------------------------------------------


class H5PLibrarySerializer(serializers.ModelSerializer):
    """Serializer for H5P libraries"""
    library_url = serializers.SerializerMethodField()
    
    class Meta:
        model = H5PLibrary
        fields = [
            'id', 'name', 'title', 'major_version', 'minor_version', 'patch_version',
            'runnable', 'preloaded_js', 'preloaded_css', 'dependencies',
            'library_path', 'library_url', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_library_url(self, obj):
        """Get the URL prefix for library assets"""
        return get_h5p_library_url(obj)


class H5PFileSerializer(serializers.ModelSerializer):
    """Serializer for H5P content files"""
    file_url = serializers.SerializerMethodField()
    
    class Meta:
        model = H5PFile
        fields = ['id', 'file', 'file_url', 'original_path', 'file_type', 'created_at']
        read_only_fields = ['id', 'created_at']
    
    def get_file_url(self, obj):
        """Get the full URL to the file"""
        if obj.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None


class H5PContentSerializer(serializers.ModelSerializer):
    """Serializer for H5P content - Full serializer with all fields (for admin/internal use)"""
    library = H5PLibrarySerializer(read_only=True)
    files = H5PFileSerializer(many=True, read_only=True)
    content_url = serializers.SerializerMethodField()
    file_urls = serializers.SerializerMethodField()
    lesson_id = serializers.SerializerMethodField()
    content_json_url = serializers.SerializerMethodField()
    embed_url = serializers.SerializerMethodField()
    library_js_urls = serializers.SerializerMethodField()
    library_css_urls = serializers.SerializerMethodField()
    h5p_core_js_urls = serializers.SerializerMethodField()
    h5p_core_css_urls = serializers.SerializerMethodField()
    
    class Meta:
        model = H5PContent
        fields = [
            'id', 'title', 'library', 'parameters', 'metadata',
            'content_path', 'content_url', 'files', 'file_urls',
            'content_json_url', 'embed_url', 'library_js_urls', 'library_css_urls',
            'h5p_core_js_urls', 'h5p_core_css_urls',
            'created_at', 'updated_at', 'lesson_id'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class H5PContentFrontendSerializer(serializers.ModelSerializer):
    """
    Optimized serializer for frontend React integration.
    Returns only the data needed to render H5P content in a clean, organized structure.
    """
    # Core content data
    content_json_url = serializers.SerializerMethodField()
    
    # H5P core files (required for all H5P content)
    core_files = serializers.SerializerMethodField()
    
    # Library files (specific to this content type)
    library_files = serializers.SerializerMethodField()
    
    # Optional context
    lesson_id = serializers.SerializerMethodField()
    
    class Meta:
        model = H5PContent
        fields = [
            'id',
            'title',
            'content_json_url',
            'core_files',
            'library_files',
            'lesson_id',
        ]
        read_only_fields = ['id']
    
    def get_lesson_id(self, obj):
        """Get the ID of the lesson this content belongs to"""
        video_lesson = obj.video_lessons.first()
        if video_lesson:
            return video_lesson.lesson.id
            
        quiz_lesson = obj.quiz_lessons.first()
        if quiz_lesson:
            return quiz_lesson.lesson.id
            
        return None
    
    def get_content_json_url(self, obj):
        """Get URL to content.json file (required for H5P rendering)"""
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(f'/api/h5p/content/{obj.id}/content.json')
        return f'/api/h5p/content/{obj.id}/content.json'
    
    def get_core_files(self, obj):
        """
        Get H5P core files organized by type.
        Returns: {
            "js": [...],  // Array of JS file URLs (load in order)
            "css": [...]  // Array of CSS file URLs
        }
        """
        request = self.context.get('request')
        core_files = get_h5p_core_files(request)
        return {
            "js": core_files.get('core_js_urls', []),
            "css": core_files.get('core_css_urls', []),
        }
    
    def get_library_files(self, obj):
        """
        Get library-specific files organized by type.
        Returns: {
            "js": [...],  // Array of library JS file URLs
            "css": [...]  // Array of library CSS file URLs
        }
        """
        request = self.context.get('request')
        
        # Get library JS URLs
        library = obj.library
        js_files = library.preloaded_js or []
        library_id = library.id
        js_urls = []
        
        for js_file in js_files:
            js_file_path = None
            
            if isinstance(js_file, dict):
                path_value = js_file.get('path', '')
                if isinstance(path_value, str):
                    js_file_path = path_value
                else:
                    continue
            elif isinstance(js_file, str):
                js_file_path = js_file
            else:
                continue
            
            if not isinstance(js_file_path, str):
                continue
            
            js_file_path = js_file_path.lstrip('/')
            if not js_file_path:
                continue
                
            if request:
                url = request.build_absolute_uri(f'/api/h5p/library/{library_id}/files/{js_file_path}')
            else:
                url = f'/api/h5p/library/{library_id}/files/{js_file_path}'
            js_urls.append(url)
        
        # Get library CSS URLs
        css_files = library.preloaded_css or []
        css_urls = []
        
        for css_file in css_files:
            css_file_path = None
            
            if isinstance(css_file, dict):
                path_value = css_file.get('path', '')
                if isinstance(path_value, str):
                    css_file_path = path_value
                else:
                    continue
            elif isinstance(css_file, str):
                css_file_path = css_file
            else:
                continue
            
            if not isinstance(css_file_path, str):
                continue
            
            css_file_path = css_file_path.lstrip('/')
            if not css_file_path:
                continue
                
            if request:
                url = request.build_absolute_uri(f'/api/h5p/library/{library_id}/files/{css_file_path}')
            else:
                url = f'/api/h5p/library/{library_id}/files/{css_file_path}'
            css_urls.append(url)
        
        return {
            "js": js_urls,
            "css": css_urls,
        }


class H5PContentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating H5P content (simpler, without nested objects)"""
    class Meta:
        model = H5PContent
        fields = ['id', 'title', 'library', 'parameters', 'metadata']


class H5PResultSerializer(serializers.ModelSerializer):
    """Serializer for H5P results"""
    class Meta:
        model = H5PResult
        fields = [
            'id', 'student', 'h5p_content', 'lesson',
            'score', 'max_score', 'opened', 'finished', 'time', 'result_json'
        ]
        read_only_fields = ['id', 'student', 'opened', 'finished']

