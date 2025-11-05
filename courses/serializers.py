from user_managment.models import *
from user_managment.serializers import UserDetailSerializer
from courses.models import *
from grading.models import *
from rest_framework import serializers
from lms_project.utils import *
from django.db.models.fields.related import ForeignKey, ManyToOneRel

from rest_framework import serializers
from django.db.models import ForeignKey

from rest_framework import serializers

class WritableNestedField(serializers.PrimaryKeyRelatedField):
    """
    Accepts an ID for writes, returns nested object for reads.
    Prevents unhashable ReturnDict errors during browsable API rendering.
    """

    def __init__(self, nested_serializer_class, **kwargs):
        self.nested_serializer_class = nested_serializer_class
        super().__init__(**kwargs)

    def get_choices(self, cutoff=None):
        """
        Override DRF’s default choice building so it uses PKs (hashable)
        instead of nested dicts during browsable API rendering.
        """
        queryset = self.get_queryset()
        if queryset is None:
            return {}
        # Build simple {pk: label} mapping
        return {item.pk: str(item) for item in queryset}

    def to_representation(self, value):
        """
        Return nested serializer for normal responses,
        but fall back to PK for form/options rendering.
        """
        # Handle PKOnlyObject (when DRF prefetches only the ID)
        if getattr(value, "_state", None) is None:  
            value = self.get_queryset().get(pk=value.pk)

        # Detect if we’re rendering HTML form or metadata
        request = self.context.get("request")
        if request and request.accepted_renderer.format == "html":
            return value.pk

        # Normal API response: return full nested representation
        return self.nested_serializer_class(value, context=self.context).data



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

        def nest_foreign_keys(current_model, depth=0, max_depth=3):
            """
            Recursively create nested serializers for ForeignKey fields
            """
            if current_model == User:
                return UserDetailSerializer

            class NestedSerializer(serializers.ModelSerializer):
                class Meta:
                    model = current_model
                    fields = "__all__"

                def __init__(self_inner, *args_inner, **kwargs_inner):
                    super().__init__(*args_inner, **kwargs_inner)
                    if depth >= max_depth:
                        return
                    for f in current_model._meta.get_fields():
                        if isinstance(f, ForeignKey):
                            self_inner.fields[f.name] = nest_foreign_keys(
                                f.related_model,
                                depth=depth + 1,
                                max_depth=max_depth
                            )(read_only=True)

            return NestedSerializer

        # # Replace ForeignKey fields with WritableNestedField - to show all nested data
        # for f in model._meta.get_fields():
        #     if isinstance(f, ForeignKey):
        #         nested_serializer_class = nest_foreign_keys(f.related_model)
        #         self.fields[f.name] = WritableNestedField(
        #             nested_serializer_class=nested_serializer_class,
        #             queryset=f.related_model.objects.all()
        #         )

        # Replace ForeignKey fields with ID-only fields - to show only IDs
        for f in model._meta.get_fields():
            if isinstance(f, ForeignKey):
                self.fields[f.name] = serializers.PrimaryKeyRelatedField(
                    queryset=f.related_model.objects.all()
                )


        # Handle reverse relations for specific models
        for f in model._meta.get_fields():
            if isinstance(f, ManyToOneRel):
                related_model = f.related_model
                related_name = f.get_accessor_name()  # this is 'attachments' in VideoLesson
                if model == VideoLesson and related_model == VideoLessonAttachment:
                    # Use a nested serializer for attachments
                    class AttachmentSerializer(serializers.ModelSerializer):
                        class Meta:
                            model = related_model
                            fields = ["id", "file", "uploaded_at"]

                    self.fields[related_name] = AttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = None
        fields = "__all__"