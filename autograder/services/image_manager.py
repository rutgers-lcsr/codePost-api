# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
"""
Image Manager - Docker image lifecycle management.

Handles versioning, cleanup, rollback, and promotion of Docker images.
"""
import logging
from typing import Optional, List, Dict, Any
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
    def record_build(cls, env: Environment, image_name: str, reason: str = "") -> int:
        """
        Add a snapshot of a successful build to the environment's history and advance its
        version. Mutates `env` only: the caller (the Builder) saves it, so there is one writer.

        Returns:
            The new version number
        """
        history = list(env.image_history or [])
        versions = [entry.get("version") or 0 for entry in history]
        # Environments built before history was kept have an image but no entry for it.
        previous = max(versions) if versions else (env.current_build_version if env.image_name else 0)
        version = previous + 1
        history.append({
            "version": version,
            "image_name": image_name,
            "requirements": env.requirements,
            "built_at": timezone.now().isoformat(),
            "status": "success",
            "reason": reason,
            "successful_runs": env.successful_runs,
            "total_runs": env.total_runs
        })
        env.image_history = history
        env.current_build_version = version
        logger.info(f"Recorded image version {version} for env {env.id}")
        return version

    @classmethod
    def image_exists(cls, image_name: Optional[str]) -> bool:
        """False only when Docker answers that the image is gone."""
        if not image_name:
            return False
        client = cls._get_docker_client()
        if not client:
            return True
        try:
            client.images.get(image_name)
            return True
        except Exception as e:
            import docker
            if isinstance(e, docker.errors.ImageNotFound):
                return False
            logger.warning(f"Could not check image {image_name}: {e}")
            return True

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
            # 1. Trim history, always keeping the snapshot of the image in use (after a
            #    rollback that is not one of the newest).
            env = Environment.objects.get(pk=environment_id)
            history = env.image_history or []
            
            deleted_count = 0
            
            if len(history) > keep_count:
                in_use = [e for e in history[:-keep_count] if e.get("image_name") == env.image_name]
                env.image_history = in_use[-1:] + history[-keep_count:]
                env.save(update_fields=['image_history'])
            
            # 2. Delete every image of this environment that nothing points at any more.
            #    Pattern: codepost-env-{id}:{timestamp}. Skipped mid-build: the image being
            #    built is not recorded yet.
            if env.build_status == 1:
                return deleted_count

            keep = {e.get("image_name") for e in (env.image_history or [])} | {env.image_name}
            image_prefix = f"codepost-env-{environment_id}:"
            
            for img in client.images.list():
                for tag in img.tags:
                    if tag.startswith(image_prefix) and tag not in keep:
                        if cls.delete_image(tag):
                            deleted_count += 1
            
            logger.info(f"Cleaned up {deleted_count} old images for env {environment_id}")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup images for env {environment_id}: {e}")
            return 0

    @classmethod
    def rollback_to_version(cls, environment_id: int, target_version: int) -> bool:
        """
        Rollback environment to a specific version: its image and its package list.

        For python and r the package lists are adjusted so the rollback sticks (see
        environment_packages.restore_snapshot). The caller queues a rebuild check, which
        rebuilds the snapshot if its image has been deleted.
        
        Args:
            environment_id: Environment ID
            target_version: Version number to rollback to
            
        Returns:
            True if rollback successful
        """
        from django.db import transaction
        from autograder.services import environment_packages as packages

        try:
            with transaction.atomic():
                env = Environment.objects.select_for_update().get(pk=environment_id)

                # Newest match: entries recorded before versions advanced all say version 1.
                target_entry = next((entry for entry in reversed(env.image_history or [])
                                     if entry.get("version") == target_version), None)
                if not target_entry:
                    logger.error(f"Version {target_version} not found in history for env {environment_id}")
                    return False

                packages.restore_snapshot(env, target_entry["requirements"])
                env.image_name = target_entry["image_name"]
                env.built_requirements = target_entry["requirements"] or ""
                # The version in use. The next build still numbers itself after the newest snapshot.
                env.current_build_version = target_version
                env.convergence_pending = False
                env.successful_runs = 0
                env.total_runs = 0
                env.save(update_fields=[
                    'image_name', 'requirements', 'built_requirements', 'current_build_version',
                    'pinned_packages', 'excluded_packages', 'convergence_pending',
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
                "last_built": env.last_built,
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

    @classmethod
    def delete_all_images_for_env(cls, environment_id: int) -> int:
        """
        Delete all images associated with an environment ID.
        Useful for cleanup after environment deletion.
        """
        client = cls._get_docker_client()
        if not client:
            return 0
            
        deleted_count = 0
        try:
            # Pattern: codepost-env-{id}*
            image_prefix = f"codepost-env-{environment_id}"
            
            all_images = client.images.list()
            for img in all_images:
                for tag in img.tags:
                    if tag.startswith(image_prefix):
                        if cls.delete_image(tag):
                             deleted_count += 1
            
            logger.info(f"Deleted {deleted_count} images for deleted env {environment_id}")
            return deleted_count
        except Exception as e:
            logger.error(f"Failed to delete images for deleted env {environment_id}: {e}")
            return deleted_count
