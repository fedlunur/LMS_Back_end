from rest_framework import serializers


class ChatbotRequestSerializer(serializers.Serializer):
    query = serializers.CharField(max_length=4000)
    session_id = serializers.CharField(max_length=200, required=False, allow_blank=True, allow_null=True)
    include_sources = serializers.BooleanField(required=False, default=False)
    data_sources = serializers.ListField(
        child=serializers.CharField(max_length=100),
        required=False,
        allow_empty=True
    )


class CreateRoomSerializer(serializers.Serializer):
    course_id = serializers.IntegerField(required=True)
    # Optional for teachers initiating a chat with a student
    student_id = serializers.IntegerField(required=False)



