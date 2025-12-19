"""
Image Manager - Docker image lifecycle management.

Handles versioning, cleanup, rollback, and promotion of Docker images.
"""
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from django.utils import timezone
from core.models import Environment

logger = logging.getLogger(__name__)

# Maximum number of image versions to keep
MAX_IMAGE_VERSIONS = 3


class ImageManager:
    """
    Manages Docker image lifecycle for environments.
    
    Features:
    - Image versioning (keeps up to MAX_IMAGE_VERSIONS)
    - Cleanup of old images
    - Rollback to previous versions
    - Promotion after successful convergence
    """

    @staticmethod
    def _get_docker_client():
        """Get Docker client."""
        try:
            import docker
            return docker.from_env()
        except Exception as e:
            logger.error(f"Failed to get Docker client: {e}")
            return None

    @classmethod
    def create_versioned_image_name(cls, assignment_id: int, version: int) -> str:
        """Generate versioned image name."""
        return f"codepost-env-{assignment_id}-v{version}"

    @classmethod
    def save_image_version(
        cls,
        environment_id: int,
        image_name: str,
        requirements: str,
        status: str = "success"
    ) -> bool:
        """
        Save a new image version to history.
        
        Args:
            environment_id: Environment ID
            image_name: Docker image name
            requirements: Requirements content at this version
            status: Build status ('success', 'failed', 'pending')
            
        Returns:
            True if saved successfully
        """
        try:
            env = Environment.objects.get(pk=environment_id)
            
            # Get current history
            history = env.image_history or []
            
            # Create new version entry
            new_entry = {
                "version": env.current_build_version,
                "image_name": image_name,
                "requirements": requirements,
                "built_at": timezone.now().isoformat(),
                "status": status,
                "successful_runs": env.successful_runs,
                "total_runs": env.total_runs
            }
            
            # Add to history
            history.append(new_entry)
            
            # Trim to max versions
            if len(history) > MAX_IMAGE_VERSIONS:
                # Get images to delete
                to_delete = history[:-MAX_IMAGE_VERSIONS]
                history = history[-MAX_IMAGE_VERSIONS:]
                
                # Schedule cleanup for old images
                for old_entry in to_delete:
                    cls.delete_image(old_entry["image_name"])
            
            # Save
            env.image_history = history
            env.save(update_fields=['image_history'])
            
            logger.info(f"Saved image version {env.current_build_version} for env {environment_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save image version for env {environment_id}: {e}")
            return False

    @classmethod
    def increment_version(cls, environment_id: int) -> int:
        """
        Increment the build version for an environment.
        
        Returns:
            New version number
        """
        try:
            env = Environment.objects.get(pk=environment_id)
            env.current_build_version += 1
            env.save(update_fields=['current_build_version'])
            return env.current_build_version
        except Exception as e:
            logger.error(f"Failed to increment version for env {environment_id}: {e}")
            return 0

    @classmethod
    def delete_image(cls, image_name: str) -> bool:
        """
        Delete a Docker image.
        
        Args:
            image_name: Full image name to delete
            
        Returns:
            True if deleted successfully
        """
        if not image_name:
            return False
            
        client = cls._get_docker_client()
        if not client:
            return False
            
        try:
            # First remove any containers using this image
            try:
                containers = client.containers.list(all=True, filters={"ancestor": image_name})
                for container in containers:
                    try:
                        container.remove(force=True)
                        logger.info(f"Deleted container {container.id} for image {image_name}")
                    except Exception as ce:
                        logger.warning(f"Failed to delete container {container.id}: {ce}")
            except Exception as ce:
                logger.warning(f"Failed to list containers for image {image_name}: {ce}")

            client.images.remove(image_name, force=True)
            logger.info(f"Deleted Docker image: {image_name}")
            return True
        except Exception as e:
            logger.warning(f"Failed to delete image {image_name}: {e}")
            return False

    @classmethod
    def cleanup_old_images(cls, environment_id: int, keep_count: int = MAX_IMAGE_VERSIONS) -> int:
        """
        Delete old image versions, keeping only the most recent N.
        
        Args:
            environment_id: Environment ID
            keep_count: Number of versions to keep
            
        Returns:
            Number of images deleted
        """
        client = cls._get_docker_client()
        if not client:
            return 0
            
        try:
            # 1. Cleanup based on History (if populated)
            env = Environment.objects.get(pk=environment_id)
            history = env.image_history or []
            
            deleted_count = 0
            
            if len(history) > keep_count:
                to_delete_history = history[:-keep_count]
                env.image_history = history[-keep_count:]
                env.save(update_fields=['image_history'])
                
                for entry in to_delete_history:
                    if cls.delete_image(entry.get("image_name")):
                        deleted_count += 1
            
            # 2. Cleanup orphaned/untagged images directly from Docker
            # Pattern: codepost-env-{id}:{timestamp}
            image_prefix = f"codepost-env-{environment_id}"
            
            all_images = client.images.list()
            matching_images = []
            
            for img in all_images:
                for tag in img.tags:
                    if tag.startswith(image_prefix + ":"):
                        try:
                            # Parse timestamp from tag
                            tag_parts = tag.split(":")
                            if len(tag_parts) == 2 and tag_parts[1].isdigit():
                                timestamp = int(tag_parts[1])
                                matching_images.append({
                                    "tag": tag,
                                    "timestamp": timestamp,
                                    "id": img.id
                                })
                        except:
                            pass
            
            # Sort by timestamp descending (newest first)
            matching_images.sort(key=lambda x: x["timestamp"], reverse=True)
            
            # Keep top N
            if len(matching_images) > keep_count:
                images_to_remove = matching_images[keep_count:]
                for img_data in images_to_remove:
                    if cls.delete_image(img_data["tag"]):
                         deleted_count += 1
            
            logger.info(f"Cleaned up {deleted_count} old images for env {environment_id}")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup images for env {environment_id}: {e}")
            return 0

    @classmethod
    def rollback_to_version(cls, environment_id: int, target_version: int) -> bool:
        """
        Rollback environment to a specific version.
        
        Args:
            environment_id: Environment ID
            target_version: Version number to rollback to
            
        Returns:
            True if rollback successful
        """
        try:
            env = Environment.objects.get(pk=environment_id)
            history = env.image_history or []
            
            # Find target version in history
            target_entry = None
            for entry in history:
                if entry.get("version") == target_version:
                    target_entry = entry
                    break
            
            if not target_entry:
                logger.error(f"Version {target_version} not found in history for env {environment_id}")
                return False
            
            # Rollback
            env.image_name = target_entry["image_name"]
            env.requirements = target_entry["requirements"]
            env.convergence_pending = False
            env.successful_runs = 0
            env.total_runs = 0
            env.save(update_fields=[
                'image_name', 'requirements', 'convergence_pending',
                'successful_runs', 'total_runs'
            ])
            
            logger.info(f"Rolled back env {environment_id} to version {target_version}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to rollback env {environment_id}: {e}")
            return False

    @classmethod
    def promote_pending_convergence(cls, environment_id: int) -> bool:
        """
        Mark pending convergence as successful.
        Clears convergence_pending flag and triggers cleanup of old versions.
        
        Args:
            environment_id: Environment ID
            
        Returns:
            True if promoted successfully
        """
        try:
            env = Environment.objects.get(pk=environment_id)
            
            if not env.convergence_pending:
                logger.warning(f"No pending convergence for env {environment_id}")
                return False
            
            env.convergence_pending = False
            env.convergence_failed_notified = False
            env.save(update_fields=['convergence_pending', 'convergence_failed_notified'])
            
            # Cleanup old versions
            cls.cleanup_old_images(environment_id)
            
            logger.info(f"Promoted convergence for env {environment_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to promote convergence for env {environment_id}: {e}")
            return False

    @classmethod
    def get_version_history(cls, environment_id: int) -> List[Dict[str, Any]]:
        """
        Get image version history for an environment.
        
        Returns:
            List of version entries
        """
        try:
            env = Environment.objects.get(pk=environment_id)
            return env.image_history or []
        except Exception as e:
            logger.error(f"Failed to get version history for env {environment_id}: {e}")
            return []

    @classmethod
    def convert_to_manual(cls, environment_id: int, from_version: Optional[int] = None) -> bool:
        """
        Convert auto-detect environment to manual configuration.
        Optionally starts from a specific version.
        
        Args:
            environment_id: Environment ID
            from_version: Optional version to use as base (uses current if None)
            
        Returns:
            True if converted successfully
        """
        try:
            env = Environment.objects.get(pk=environment_id)
            
            if from_version is not None:
                # Find version in history
                for entry in (env.image_history or []):
                    if entry.get("version") == from_version:
                        env.requirements = entry["requirements"]
                        env.image_name = entry["image_name"]
                        break
            
            env.auto_detect = False
            env.convergence_pending = False
            env.convergence_stats = {}
            env.save(update_fields=[
                'auto_detect', 'convergence_pending', 'convergence_stats',
                'requirements', 'image_name'
            ])
            
            logger.info(f"Converted env {environment_id} to manual config")
            return True
            
        except Exception as e:
            logger.error(f"Failed to convert env {environment_id} to manual: {e}")
            return False

    @classmethod
    def get_current_status(cls, environment_id: int) -> Dict[str, Any]:
        """
        Get current environment status for UI display.
        
        Returns:
            Status dict with version info, health metrics, etc.
        """
        try:
            env = Environment.objects.get(pk=environment_id)
            
            success_rate = 0
            if env.total_runs > 0:
                success_rate = (env.successful_runs / env.total_runs) * 100
            
            return {
                "environment_id": environment_id,
                "auto_detect": env.auto_detect,
                "current_version": env.current_build_version,
                "image_name": env.image_name,
                "build_status": env.build_status,
                "last_built": env.last_built.isoformat() if env.last_built else None,
                "successful_runs": env.successful_runs,
                "total_runs": env.total_runs,
                "success_rate": round(success_rate, 1),
                "convergence_pending": env.convergence_pending,
                "pending_modules": list(env.convergence_stats.keys()) if env.convergence_stats else [],
                "version_history": env.image_history or [],
                "history_count": len(env.image_history or [])
            }
            
        except Exception as e:
            logger.error(f"Failed to get status for env {environment_id}: {e}")
            return {}
