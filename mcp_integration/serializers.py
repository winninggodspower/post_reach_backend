from rest_framework import serializers


class OAuthConnectionSerializer(serializers.Serializer):
    client_id = serializers.CharField()
    client_name = serializers.CharField()
    scopes = serializers.ListField(child=serializers.CharField())
    connected_at = serializers.DateTimeField()
    expires_at = serializers.DateTimeField()
