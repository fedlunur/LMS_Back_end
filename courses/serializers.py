from user_managment.models import *
from courses.models import *
from grading.models import *
from rest_framework import serializers
from lms_project.utils import *
from django.db.models.fields.related import ForeignKey



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

        # Dynamically set Meta
        self.Meta.model = model
        self.Meta.fields = "__all__"

        super().__init__(*args, **kwargs)

        # Recursive function to create nested serializers
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

        # Replace ForeignKey fields in main serializer
        for f in model._meta.get_fields():
            if isinstance(f, ForeignKey):
                self.fields[f.name] = nest_foreign_keys(f.related_model)(read_only=True)

    class Meta:
        model = None
        fields = "__all__"

