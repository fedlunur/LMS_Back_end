from django.apps import apps
from django.db.models import ForeignKey, ManyToOneRel
from rest_framework import serializers
from user_managment.models import User
from user_managment.serializers import UserDetailSerializer

# Import your attachment models
from courses.models import *  # Add more if needed


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


# Automatically map all models in 'courses' app
all_models = apps.get_app_config('courses').get_models()
model_mapping = {model.__name__.lower(): model for model in all_models}

# Define which lesson types have attachments
LESSON_TYPES_WITH_ATTACHMENTS = ["VideoLesson", "ArticleLesson", "QuizLesson", "AssignmentLesson"]


class DynamicFieldSerializer(serializers.ModelSerializer):
    def __init__(self, *args, **kwargs):
        model_name = kwargs.pop("model_name", None)
        if not model_name:
            super().__init__(*args, **kwargs)
            return

        model_name_lower = model_name.lower()
        model = model_mapping.get(model_name_lower)
        if not model:
            raise ValueError(f"Invalid model name: {model_name}")

        self.Meta.model = model
        self.Meta.fields = "__all__"
        super().__init__(*args, **kwargs)

        # Add model properties as read-only fields
        for attr_name in dir(model):
            attr = getattr(model, attr_name, None)
            if isinstance(attr, property):
                self.fields[attr_name] = serializers.ReadOnlyField()

        # Handle ForeignKey fields
        for f in model._meta.get_fields():
            if isinstance(f, ForeignKey):
                self.fields[f.name] = serializers.PrimaryKeyRelatedField(
                    queryset=f.related_model.objects.all()
                )

        # Handle reverse relations for attachments and external links if it's a lesson type
        if model.__name__ in LESSON_TYPES_WITH_ATTACHMENTS:
            for f in model._meta.get_fields():
                if isinstance(f, ManyToOneRel):
                    related_model = f.related_model
                    related_name = f.get_accessor_name()
                    
                    # Handle attachments
                    if "attachment" in related_model.__name__.lower() or f.name == "attachments":
                        class AttachmentSerializer(serializers.ModelSerializer):
                            class Meta:
                                model = related_model
                                fields = ["id", "file", "uploaded_at"] if hasattr(related_model, "file") else "__all__"
                        self.fields[related_name] = AttachmentSerializer(many=True, read_only=True)

                    # Handle external links
                    elif "externallink" in related_model.__name__.lower() or f.name == "external_links_items":
                        class ExternalLinkSerializer(serializers.ModelSerializer):
                            class Meta:
                                model = related_model
                                fields = ["id", "title", "url", "description"]
                        self.fields[related_name] = ExternalLinkSerializer(many=True, read_only=True)

    class Meta:
        model = None
        fields = "__all__"

    # ----------------- CREATE & UPDATE -----------------
    def create(self, validated_data):
        model = self.Meta.model
        attachments = validated_data.pop("attachments", None)
        lesson_instance = validated_data.pop("lesson", None)

        if lesson_instance and model.__name__ in LESSON_TYPES_WITH_ATTACHMENTS:
            obj, created = model.objects.update_or_create(
                lesson=lesson_instance,
                defaults=validated_data
            )
            if attachments:
                if hasattr(obj, "attachments"):
                    obj.attachments.all().delete()
                    for f in attachments:
                        related_model = obj._meta.get_field("attachments").related_model
                        related_model.objects.create(**{obj._meta.model_name: obj, "file": f})
            return obj

        return super().create(validated_data)

    def update(self, instance, validated_data):
        model = self.Meta.model
        attachments = validated_data.pop("attachments", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if attachments and hasattr(instance, "attachments"):
            instance.attachments.all().delete()
            for f in attachments:
                related_model = instance._meta.get_field("attachments").related_model
                related_model.objects.create(**{instance._meta.model_name: instance, "file": f})

        return instance


# from user_managment.models import *
# from courses.models import *
# from grading.models import *
# from rest_framework import serializers
# from lms_project.utils import *
# from django.db.models.fields.related import ForeignKey


# from rest_framework import serializers
# from django.db.models import ForeignKey

# class WritableNestedField(serializers.PrimaryKeyRelatedField):
#     """
#     Accepts an ID for writes, returns nested object for reads.
#     Handles PKOnlyObject correctly.
#     """
#     def __init__(self, nested_serializer_class, **kwargs):
#         self.nested_serializer_class = nested_serializer_class
#         super().__init__(**kwargs)

#     def to_representation(self, value):
#         # If DRF passed a PKOnlyObject, fetch the real instance
#         if getattr(value, "_state", None) is None:  # PKOnlyObject
#             value = self.get_queryset().get(pk=value.pk)
#         return self.nested_serializer_class(value, context=self.context).data



# class DynamicFieldSerializer(serializers.ModelSerializer):
#     def __init__(self, *args, **kwargs):
#         model_name = kwargs.pop("model_name", None)
#         if not model_name:
#             super().__init__(*args, **kwargs)
#             return

#         model_name_lower = model_name.lower()
#         model = model_mapping.get(model_name_lower)
#         if not model:
#             raise ValueError(f"Invalid model name: {model_name}")

#         self.Meta.model = model
#         self.Meta.fields = "__all__"

#         super().__init__(*args, **kwargs)

#         def nest_foreign_keys(current_model, depth=0, max_depth=3):
#             """
#             Recursively create nested serializers for ForeignKey fields
#             """
#             class NestedSerializer(serializers.ModelSerializer):
#                 class Meta:
#                     model = current_model
#                     fields = "__all__"

#                 def __init__(self_inner, *args_inner, **kwargs_inner):
#                     super().__init__(*args_inner, **kwargs_inner)
#                     if depth >= max_depth:
#                         return
#                     for f in current_model._meta.get_fields():
#                         if isinstance(f, ForeignKey):
#                             self_inner.fields[f.name] = nest_foreign_keys(
#                                 f.related_model,
#                                 depth=depth + 1,
#                                 max_depth=max_depth
#                             )(read_only=True)

#             return NestedSerializer

#         # Replace ForeignKey fields with WritableNestedField
#         for f in model._meta.get_fields():
#             if isinstance(f, ForeignKey):
#                 nested_serializer_class = nest_foreign_keys(f.related_model)
#                 self.fields[f.name] = WritableNestedField(
#                     nested_serializer_class=nested_serializer_class,
#                     queryset=f.related_model.objects.all()
#                 )

#     class Meta:
#         model = None
#         fields = "__all__"

