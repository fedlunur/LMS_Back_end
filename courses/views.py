from django.shortcuts import render

# Create your views here.
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from .serializers import DynamicFieldSerializer, model_mapping
from .UtilMethods import *
class GenericModelViewSet(viewsets.ModelViewSet):
    pagination_class = CustomPagination

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [AllowAny()]
        return [IsAuthenticated()]

    # def get_queryset(self):
    #     model = model_mapping.get(self.basename.lower())
    #     if not model:
    #         raise AssertionError(f"Model not found for basename '{self.basename}'")
    #     return model.objects.all()
    def get_queryset(self):
            model = model_mapping.get(self.basename.lower())
            if not model:
                raise AssertionError(f"Model not found for basename '{self.basename}'")

            queryset = model.objects.all()

            # 🔹 Dynamic filtering by query params
            filter_kwargs = {}
            for field, value in self.request.query_params.items():
                if field in [f.name for f in model._meta.get_fields()]:
                    filter_kwargs[field] = value

            if filter_kwargs:
                queryset = queryset.filter(**filter_kwargs)

            return queryset


    def get_serializer(self, *args, **kwargs):
        kwargs["model_name"] = self.basename
        return DynamicFieldSerializer(*args, **kwargs)

    # Unified success/failure responses
    def success_response(self, data, message, code=status.HTTP_200_OK):
        return Response({"success": True, "data": data, "message": message}, status=code)

    def failure_response(self, message, code=status.HTTP_400_BAD_REQUEST):
        return Response({"success": False, "message": message}, status=code)

    # Only override where needed
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            if self.basename.lower() == "course":
                # Pass get_serializer method to the handler so it can serialize instance properly
                return handle_course_create_or_update(request, serializer.__class__, self.get_serializer)
            else:
                instance = serializer.save()
                return self.success_response(self.get_serializer(instance).data, "Created successfully", status.HTTP_201_CREATED)

        return self.failure_response(serializer.errors)    

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        if serializer.is_valid():
            serializer.save()
            return self.success_response(serializer.data, "Updated successfully")
        return self.failure_response(serializer.errors)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return self.success_response({}, "Deleted successfully")
        
    def list(self, request, *args, **kwargs):
            queryset = self.filter_queryset(self.get_queryset())

            # Apply pagination
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                # Wrap DRF's paginated response
                return self.get_paginated_response({
                    "success": True,
                    "data": serializer.data,
                    "message": "Records retrieved successfully."
                })

            # If no pagination
            serializer = self.get_serializer(queryset, many=True)
            return self.success_response(serializer.data, "Records retrieved successfully.")
    
    
       