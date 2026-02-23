# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
"""
Execution Result Serializers

Provides properly typed serializers for code execution endpoints.
These serializers ensure the auto-generated SDK has complete type definitions.
"""

from rest_framework import serializers


# =============================================================================
# Request Serializers
# =============================================================================

class FileExecutionRequestSerializer(serializers.Serializer):
    """Request serializer for file execution endpoints"""
    file_id = serializers.IntegerField(
        help_text="ID of the file to execute"
    )
    timeout = serializers.IntegerField(
        required=False, 
        default=30,
        min_value=1,
        max_value=120,
        help_text="Execution timeout in seconds (1-120)"
    )
    force_execute = serializers.BooleanField(
        required=False, 
        default=False,
        help_text="If true, bypass cache and force new execution"
    )
    test_code = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Optional test script to inject during execution"
    )
    code_override = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Optional content override for the file (e.g., edited notebook JSON)"
    )

    # Accept both camelCase (from generated TS client) and snake_case
    CAMEL_TO_SNAKE = {
        'fileId': 'file_id',
        'forceExecute': 'force_execute',
        'testCode': 'test_code',
        'codeOverride': 'code_override',
    }

    def to_internal_value(self, data):
        data = data.copy() if hasattr(data, 'copy') else dict(data)
        for camel, snake in self.CAMEL_TO_SNAKE.items():
            if camel in data and snake not in data:
                data[snake] = data.pop(camel)
        return super().to_internal_value(data)


class AsyncExecutionRequestSerializer(FileExecutionRequestSerializer):
    """Request serializer for async execution"""
    example_code = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Optional example code to inject during execution"
    )

    CAMEL_TO_SNAKE = {
        **FileExecutionRequestSerializer.CAMEL_TO_SNAKE,
        'exampleCode': 'example_code',
    }


class CodeExecutionRequestSerializer(serializers.Serializer):
    """Request serializer for code execution"""
    code = serializers.CharField(help_text="Code to execute")
    language = serializers.CharField(help_text="Language for execution")
    timeout = serializers.IntegerField(required=False, default=30, min_value=1, max_value=300)
    working_dir = serializers.CharField(required=False, allow_null=True)


class NotebookExecutionRequestSerializer(serializers.Serializer):
    """Request serializer for notebook execution"""
    notebook_content = serializers.CharField(help_text="Notebook JSON content")
    timeout = serializers.IntegerField(required=False, default=60, min_value=1, max_value=300)
    kernel_name = serializers.CharField(required=False, default="python3")


class NotebookCellExecutionRequestSerializer(serializers.Serializer):
    """Request serializer for executing a single notebook cell"""
    cell_code = serializers.CharField(help_text="Cell code to execute")
    cell_index = serializers.IntegerField(required=False, default=0)
    timeout = serializers.IntegerField(required=False, default=30, min_value=1, max_value=300)
    kernel_name = serializers.CharField(required=False, default="python3")


class TestExecutionRequestSerializer(serializers.Serializer):
    """Request serializer for running tests"""
    testId = serializers.IntegerField(
        required=False, 
        allow_null=True,
        help_text="ID of the test to run. If null, runs all tests."
    )
    submissionId = serializers.IntegerField(
        help_text="ID of the submission to test"
    )
    file_overrides = serializers.DictField(
        child=serializers.CharField(),
        required=False,
        default=dict,
        help_text="Map of file ID to temporary content for ephemeral execution"
    )

    def to_internal_value(self, data):
        data = data.copy() if hasattr(data, 'copy') else dict(data)
        if 'fileOverrides' in data and 'file_overrides' not in data:
            data['file_overrides'] = data.pop('fileOverrides')
        return super().to_internal_value(data)


# =============================================================================
# Cell Output Serializers (nbformat v4 compatible)
# =============================================================================

class NotebookStreamOutputSerializer(serializers.Serializer):
    """Stream output (stdout/stderr) from a notebook cell"""
    output_type = serializers.ChoiceField(
        choices=['stream'],
        help_text="Output type identifier"
    )
    name = serializers.ChoiceField(
        choices=['stdout', 'stderr'],
        help_text="Stream name"
    )
    text = serializers.CharField(
        help_text="Output text content"
    )


class NotebookExecuteResultSerializer(serializers.Serializer):
    """Execute result from a code cell (return value)"""
    output_type = serializers.ChoiceField(
        choices=['execute_result'],
        help_text="Output type identifier"
    )
    data = serializers.DictField(
        help_text="MIME-type keyed output data (e.g., {'text/plain': '...', 'image/png': '...'})"
    )
    metadata = serializers.DictField(
        required=False,
        default={},
        help_text="Output metadata"
    )
    execution_count = serializers.IntegerField(
        allow_null=True,
        help_text="Cell execution count"
    )


class NotebookDisplayDataSerializer(serializers.Serializer):
    """Display data output (images, HTML, etc.)"""
    output_type = serializers.ChoiceField(
        choices=['display_data'],
        help_text="Output type identifier"
    )
    data = serializers.DictField(
        help_text="MIME-type keyed display data"
    )
    metadata = serializers.DictField(
        required=False,
        default={},
        help_text="Display metadata"
    )


class NotebookErrorOutputSerializer(serializers.Serializer):
    """Error output from a cell"""
    output_type = serializers.ChoiceField(
        choices=['error'],
        help_text="Output type identifier"
    )
    ename = serializers.CharField(help_text="Exception name/class")
    evalue = serializers.CharField(help_text="Exception value/message")
    traceback = serializers.ListField(
        child=serializers.CharField(),
        help_text="Formatted traceback lines"
    )


class NotebookCellOutputSerializer(serializers.Serializer):
    """
    Union serializer for all notebook cell output types.
    
    In practice, each output will be ONE of:
    - stream (stdout/stderr)  
    - execute_result (return value)
    - display_data (images, html, etc)
    - error (exceptions)
    """
    output_type = serializers.ChoiceField(
        choices=['stream', 'execute_result', 'display_data', 'error'],
        help_text="Type of cell output"
    )
    # Stream fields
    name = serializers.CharField(required=False, help_text="Stream name for stream outputs")
    text = serializers.CharField(required=False, help_text="Text content for stream outputs")
    # Result/Display fields  
    data = serializers.DictField(required=False, help_text="MIME-type keyed data")
    metadata = serializers.DictField(required=False, help_text="Output metadata")
    execution_count = serializers.IntegerField(required=False, allow_null=True)
    # Error fields
    ename = serializers.CharField(required=False, help_text="Exception name")
    evalue = serializers.CharField(required=False, help_text="Exception value")
    traceback = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="Formatted traceback"
    )


# =============================================================================
# Notebook Cell & Structure Serializers
# =============================================================================

class NotebookCellSerializer(serializers.Serializer):
    """A cell in a Jupyter notebook (nbformat v4)"""
    cell_type = serializers.ChoiceField(
        choices=['code', 'markdown', 'raw'],
        help_text="Type of cell"
    )
    source = serializers.CharField(
        help_text="Cell source content"
    )
    outputs = NotebookCellOutputSerializer(
        many=True,
        required=False,
        help_text="Cell outputs (code cells only)"
    )
    execution_count = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="Execution order number (code cells only)"
    )
    metadata = serializers.DictField(
        required=False,
        default={},
        help_text="Cell metadata"
    )


class NotebookOutputDataSerializer(serializers.Serializer):
    """Output data for notebook execution results"""
    cells = NotebookCellSerializer(
        many=True,
        help_text="Executed notebook cells with outputs"
    )
    notebook = serializers.CharField(
        required=False,
        help_text="Full notebook JSON string (if available)"
    )
    system_logs = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="System-level execution logs"
    )


# =============================================================================
# Base Execution Result Serializers
# =============================================================================

class ExecutionResultSerializer(serializers.Serializer):
    """
    Standard execution result for code files and notebooks.
    
    This is the primary response type for all execution endpoints.
    """
    success = serializers.BooleanField(
        help_text="Whether execution completed successfully"
    )
    stdout = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Standard output from execution"
    )
    stderr = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Standard error from execution"
    )
    error = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="Error message if execution failed"
    )
    execution_time = serializers.FloatField(
        required=False,
        help_text="Execution duration in seconds"
    )
    output_data = serializers.DictField(
        required=False,
        help_text="Structured output data (notebook cells, images, etc.)"
    )
    system_logs = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="System-level logs from the executor"
    )
    tests = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        help_text="Structured test results (if present)"
    )
    timestamp = serializers.DateTimeField(
        required=False,
        help_text="When the execution completed"
    )


class StreamingExecutionResultSerializer(ExecutionResultSerializer):
    """Extended execution result with file context for streaming endpoints"""
    file_id = serializers.IntegerField(
        help_text="ID of the executed file"
    )
    file_name = serializers.CharField(
        help_text="Name of the executed file"
    )
    cached = serializers.BooleanField(
        help_text="Whether result was served from cache"
    )
    submission_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="ID of the associated submission (if applicable)"
    )


# =============================================================================
# Cache Check Serializers
# =============================================================================

class CacheCheckResponseSerializer(serializers.Serializer):
    """Response for cache check endpoint"""
    has_cache = serializers.BooleanField(
        help_text="Whether a cached execution result exists"
    )
    execution_time = serializers.FloatField(
        required=False,
        help_text="Execution time of cached result (if has_cache)"
    )
    executed_at = serializers.DateTimeField(
        required=False,
        allow_null=True,
        help_text="When the cached execution was performed (staff only)"
    )
    executed_by = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="Username who executed the code (staff only)"
    )


# =============================================================================
# Async Task Serializers  
# =============================================================================

class AsyncTaskResponseSerializer(serializers.Serializer):
    """Response for async execution task creation"""
    task_id = serializers.CharField(
        help_text="Celery task ID for tracking execution"
    )
    status = serializers.CharField(
        help_text="Initial task status (typically 'queued')"
    )


class TaskStatusResponseSerializer(serializers.Serializer):
    """Response for task status check"""
    status = serializers.ChoiceField(
        choices=['PENDING', 'STARTED', 'SUCCESS', 'FAILURE', 'RETRY', 'REVOKED'],
        help_text="Current task status"
    )
    result = serializers.DictField(
        required=False,
        allow_null=True,
        help_text="Task result (if completed)"
    )


# =============================================================================
# Test Execution Serializers
# =============================================================================

class TestExecutionResultSerializer(serializers.Serializer):
    """Response for test execution"""
    success = serializers.BooleanField(
        help_text="Whether the test execution completed"
    )
    result = serializers.JSONField(
        required=False,
        help_text="Test result details (object or list)"
    )
    error = serializers.CharField(
        required=False,
        help_text="Error message if test failed"
    )


# =============================================================================
# Shell Metrics Serializers
# =============================================================================

class ShellMetricsSessionSerializer(serializers.Serializer):
    """Serializer for a single shell session metrics payload"""
    sessionId = serializers.CharField(required=False)
    lastActivity = serializers.FloatField(required=False, allow_null=True)


class ShellMetricsResponseSerializer(serializers.Serializer):
    """Response serializer for shell metrics endpoint"""
    activeCount = serializers.IntegerField()
    inCount = serializers.IntegerField()
    outCount = serializers.IntegerField()
    workerCount = serializers.IntegerField()
    workerIds = serializers.ListField(child=serializers.CharField(), required=False)
    activeIds = serializers.ListField(child=serializers.CharField(), required=False)
    redisUrl = serializers.CharField(required=False)
    sessions = ShellMetricsSessionSerializer(many=True, required=False)
