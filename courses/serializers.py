from django.apps import apps
from django.db.models import ForeignKey, ManyToOneRel, FileField, ImageField
from rest_framework import serializers
from user_managment.models import User
from user_managment.serializers import UserDetailSerializer
from django.conf import settings

# Import your attachment models
from courses.models import *  # Add more if needed

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
