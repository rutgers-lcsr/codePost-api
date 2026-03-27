# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial Licensed, included with this software.
from rest_framework import serializers
from core.models import ChatConversation, ChatMessage


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ('id', 'role', 'content', 'tool_name', 'tool_args', 'tool_status', 'token_count', 'created')
        read_only_fields = fields


class ChatConversationListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing conversations (no messages)."""
    messageCount = serializers.SerializerMethodField()

    class Meta:
        model = ChatConversation
        fields = ('id', 'submission', 'assignment', 'title', 'summary', 'messageCount', 'created', 'modified')
        read_only_fields = ('id', 'assignment', 'summary', 'messageCount', 'created', 'modified')

    def get_messageCount(self, obj) -> int:
        return obj.messages.count()


class ChatConversationDetailSerializer(serializers.ModelSerializer):
    """Full serializer for retrieving a conversation with messages."""
    messages = ChatMessageSerializer(many=True, read_only=True)
    messageCount = serializers.SerializerMethodField()

    class Meta:
        model = ChatConversation
        fields = ('id', 'submission', 'assignment', 'title', 'summary', 'messageCount', 'messages', 'created', 'modified')
        read_only_fields = ('id', 'assignment', 'summary', 'messageCount', 'messages', 'created', 'modified')

    def get_messageCount(self, obj) -> int:
        return obj.messages.count()


class ChatConversationCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a new conversation."""

    class Meta:
        model = ChatConversation
        fields = ('id', 'submission', 'title', 'created', 'modified')
        read_only_fields = ('id', 'created', 'modified')
