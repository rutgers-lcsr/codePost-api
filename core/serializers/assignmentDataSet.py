from rest_framework import serializers

from core.models import AssignmentDataSet


class AssignmentDataSetSerializer(serializers.ModelSerializer):
    """Serializer for AssignmentDataSet model"""
    
    # Read-only computed fields
    file_url = serializers.SerializerMethodField()
    file_size = serializers.SerializerMethodField()
    file_name = serializers.SerializerMethodField()
    
    class Meta:
        model = AssignmentDataSet
        fields = [
            'id',
            'assignment',
            'name',
            'description',
            'file',
            'file_url',
            'file_size',
            'file_name',
            'mount_path',
            'is_active',
            'created',
            'modified',
        ]
        read_only_fields = ['id', 'created', 'modified', 'file_url', 'file_size', 'file_name']
    
    def get_file_url(self, obj):
        """Get the URL to download the dataset file"""
        if obj.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None
    
    def get_file_size(self, obj):
        """Get the size of the dataset file in bytes"""
        if obj.file:
            try:
                return obj.file.size
            except:
                return None
        return None
    
    def get_file_name(self, obj):
        """Get the original filename"""
        if obj.file:
            try:
                return obj.file.name.split('/')[-1]
            except:
                return None
        return None


class AssignmentDataSetCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating AssignmentDataSet"""
    
    class Meta:
        model = AssignmentDataSet
        fields = [
            'assignment',
            'name',
            'description',
            'file',
            'mount_path',
            'is_active',
        ]
    
    def validate_file(self, value):
        """Validate file size"""
        # Check file size (limit to 1GB)
        max_size = 1024 * 1024 * 1024  # 1GB
        if value.size > max_size:
            raise serializers.ValidationError(
                f"File size exceeds maximum allowed size of {max_size / (1024**3):.1f} GB"
            )
        
        return value


class AssignmentDataSetUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating AssignmentDataSet (without file upload)"""
    
    class Meta:
        model = AssignmentDataSet
        fields = [
            'name',
            'description',
            'mount_path',
            'is_active',
        ]
