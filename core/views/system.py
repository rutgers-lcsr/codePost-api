# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.decorators import api_view, permission_classes
from drf_spectacular.utils import extend_schema, OpenApiParameter
from django.db import connection, DatabaseError
from log.models import Event
from django.core.paginator import Paginator

from core.serializers.system import SystemHealthResponseSerializer, SystemActivityResponseSerializer
# Optional: import celery for status check, or just check queue?
# For now, we will do a simple DB check. Celery check is harder without celery-result-backend query or flower.

class SystemHealthView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    @extend_schema(responses={200: SystemHealthResponseSerializer})
    def get(self, request):
        health = {
            "database": "Unknown",
            "celery": "Unknown", # Placeholder
        }

        # Check Database
        try:
            connection.ensure_connection()
            health["database"] = "Connected"
        except DatabaseError:
            health["database"] = "Disconnected"

        # Check Celery (simple heuristic: are there recent tasks? or just assume running if no error?)
        # A better check would be pinging a worker, but that's async.
        # We'll default to "Unknown" or "Assumed Running" for MVP, or check if we can import current app
        try:
            from autograder.celery import app
            # forceful ping?
            # i = app.control.inspect()
            # if i.ping(): health["celery"] = "Running"
            # else: health['celery'] = "Stopped"
            # Note: control.inspect() can be slow/timeout.
            health["celery"] = "Running (Assumed)" 
        except Exception as e:
            print(f"Celery Health Check Failed: {e}")
            health["celery"] = "Error Checking"

        return Response(health)

class SystemActivityView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    @extend_schema(
        responses={200: SystemActivityResponseSerializer},
        parameters=[
            OpenApiParameter(name="page", required=False, type=int, location=OpenApiParameter.QUERY),
            OpenApiParameter(name="pageSize", required=False, type=int, location=OpenApiParameter.QUERY),
        ],
    )
    def get(self, request):
        # Fetch recent events
        page_size = int(request.query_params.get('pageSize', 20))
        page_num = int(request.query_params.get('page', 1))

        events = Event.objects.all().order_by('-created')
        paginator = Paginator(events, page_size)
        page = paginator.get_page(page_num)

        data = []
        for event in page:
            data.append({
                "id": event.id,
                "category": event.category,
                "description": event.description,
                "created": event.created,
                "meta": event.meta,
                "courseID": event.courseID,
                "user": event.user
            })

        return Response({
            "results": data,
            "total": paginator.count,
            "page": page_num,
            "pages": paginator.num_pages
        })

