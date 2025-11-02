from user_managment.models import *
from courses.models import *
from grading.models import *
from rest_framework import serializers
from lms_project.utils import *
from django.db.models.fields.related import ForeignKey


from rest_framework import serializers
from django.db.models import ForeignKey

class WritableNestedField(serializers.PrimaryKeyRelatedField):
    """
    Accepts an ID for writes, returns nested object for reads.
    Handles PKOnlyObject correctly.
    """
    def __init__(self, nested_serializer_class, **kwargs):
        self.nested_serializer_class = nested_serializer_class
        super().__init__(**kwargs)

    def to_representation(self, value):
        # If DRF passed a PKOnlyObject, fetch the real instance
        if getattr(value, "_state", None) is None:  # PKOnlyObject
            value = self.get_queryset().get(pk=value.pk)
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

        # Replace ForeignKey fields with WritableNestedField
        for f in model._meta.get_fields():
            if isinstance(f, ForeignKey):
                nested_serializer_class = nest_foreign_keys(f.related_model)
                self.fields[f.name] = WritableNestedField(
                    nested_serializer_class=nested_serializer_class,
                    queryset=f.related_model.objects.all()
                )

    class Meta:
        model = None
        fields = "__all__"