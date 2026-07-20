# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from rest_framework import serializers

from core.models import StudentDataSetAssignment


class StudentDataSetAssignmentSerializer(serializers.ModelSerializer):
    """Staff-facing view of one student's dataset-variant assignment. `dataset` is the
    only writable field (staff overriding the auto-assignment) — `assignedBy` is set
    server-side to the requesting staff member."""

    studentEmail = serializers.EmailField(source='student.email', read_only=True)
    datasetName = serializers.CharField(source='dataset.name', read_only=True)
    assignedByEmail = serializers.EmailField(source='assignedBy.email', read_only=True, allow_null=True)

    class Meta:
        model = StudentDataSetAssignment
        fields = ('id', 'assignment', 'student', 'studentEmail', 'dataset', 'datasetName',
                  'assignedBy', 'assignedByEmail', 'created', 'modified')
        read_only_fields = ('id', 'assignment', 'student', 'assignedBy', 'created', 'modified')

    def validate_dataset(self, value):
        if self.instance is not None and value.assignment_id != self.instance.assignment_id:
            raise serializers.ValidationError("The dataset must belong to the same assignment.")
        if not value.is_student_variant:
            raise serializers.ValidationError("Only per-student variant datasets can be assigned.")
        return value
