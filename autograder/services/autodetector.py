# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
import logging
import json
import re
import time
from typing import List, Dict, Optional, Tuple, Any
from django.db.models import Count
from core.models import Submission, SubmissionFile, Assignment
from core.constants import NON_CODE_EXTENSIONS
from log.models import Event
from core.services.file_handlers.factory import FileHandlerFactory

logger = logging.getLogger(__name__)

# Requirement formats that are one package per line and so can be merged line by line.
# Everything else (pom.xml, package.json, Gemfile, composer.json, Makefile) is a
# whole-file manifest that must never be split, deduped or sorted line by line.
LINE_ORIENTED_FAMILIES = ('python', 'r')

# A PyPI answer (exists / does not) is cached this long; failed lookups are never cached.
PYPI_CACHE_SECONDS = 24 * 60 * 60


class Autodetector:
    """
    Service to detect environment settings (Language, Dependencies) from submission files.
    Refactored to use FileHandlers.
    """

    @staticmethod
    def collect_local_modules(files: List[Any]) -> set:
        """
        Names of modules provided by the files themselves (client.py -> client, or
        client/api/notebook.py -> client), which must not be installed from PyPI.
        """
        local_modules = set()
        for f in files:
            # f.name might contain path separators if uploaded as such; File models also have a path
            full_paths = [f.name]
            if getattr(f, 'path', None):
                full_paths.append(f"{f.path}/{f.name}")

            for p in full_paths:
                p = p.replace('\\', '/')
                parts = p.split('/')
                if len(parts) > 1:
                    # Directory structure: the top-level folder is likely the package name
                    local_modules.add(parts[0])
                elif p.endswith('.py'):
                    local_modules.add(p[:-3])
        return local_modules

    @staticmethod
    def merge_requirements(language: str, blobs: List[str], local_modules: Optional[set] = None,
                           check_pypi: bool = True, uploaded_manifests: Optional[List[str]] = None) -> Optional[str]:
        """
        The one place that combines per-file requirement strings into an Environment's requirements.

        Line-oriented formats (python, r) are merged per line: local modules are dropped, python
        packages must exist on PyPI, and the result is deduped and sorted. Whole-file manifests are
        kept intact; when several distinct ones exist they are merged structurally (package.json
        dependencies, pom.xml <dependency> blocks) or the first one wins.

        uploaded_manifests are instructor-uploaded manifest files (package.json, pom.xml, ...); the first
        is the base (its non-dependency fields win) and the auto-detected `blobs` are merged into it.

        check_pypi=False skips the PyPI existence lookup (a network call), for callers inside an HTTP
        request; the build path re-runs detection with the check before building.
        """
        family = (language or '').lower().split('-')[0]
        local_modules = local_modules or set()

        if family in LINE_ORIENTED_FAMILIES:
            packages = set()
            for blob in blobs:
                for req in blob.split('\n'):
                    req = req.strip()
                    if not req or req in packages:
                        continue
                    if req in local_modules:
                        logger.info(f"[AutoDetect] Filtering local module '{req}' (found key in local files)")
                        continue
                    if family == 'python' and check_pypi and not Autodetector.check_pypi_existence(req):
                        logger.warning(f"[AutoDetect] Package '{req}' not found on PyPI. Assuming local/private module and skipping.")
                        continue
                    packages.add(req)
            return "\n".join(sorted(packages)) if packages else None

        manifests: List[str] = []
        for blob in list(uploaded_manifests or []) + list(blobs):
            if blob and blob.strip() and blob not in manifests:
                manifests.append(blob)
        if not manifests:
            return None
        base, others = manifests[0], manifests[1:]
        for other in others:
            base = Autodetector._merge_manifests(base, other)
        return base

    @staticmethod
    def _merge_manifests(base: str, other: str) -> str:
        """Fold the dependencies of `other` into `base`; unmergeable formats keep `base`."""
        try:
            a, b = json.loads(base), json.loads(other)
        except ValueError:
            a = b = None
        if isinstance(a, dict) and isinstance(b, dict):
            for key in ('dependencies', 'devDependencies'):
                if isinstance(b.get(key), dict):
                    merged = dict(b[key])
                    if isinstance(a.get(key), dict):
                        merged.update(a[key])
                    a[key] = merged
            return json.dumps(a, indent=2)

        if '</dependencies>' in base:
            squash = lambda block: re.sub(r'\s+', '', block)
            known = {squash(x) for x in re.findall(r'<dependency>.*?</dependency>', base, re.S)}
            extra = [x for x in re.findall(r'<dependency>.*?</dependency>', other, re.S) if squash(x) not in known]
            if extra:
                head, _, tail = base.rpartition('</dependencies>')
                return head + "\n    ".join([''] + extra) + "\n  </dependencies>" + tail
        return base

    @staticmethod
    def detect_from_files(files: List[Any], assignment: Any = None, check_pypi: bool = True) -> Optional[Tuple[str, str | None]]:
        """
        Detects language and requirements from a list of file dicts.
        Args:
            files: List of dicts {'name': str, 'extension': str, 'data'/'code': str}
                   OR Django model instances (SubmissionFile, AssignmentFile)
        """
        language_counts: Dict[str, int] = {}
        active_files = [] # Files that can provide requirements

        for f in files:
            # Normalize to object-like structure for the Factory
            # The Factory expects a File-like object with name, extension, data/code
            
            if isinstance(f, dict):
                 # Create a lightweight dummy object
                 class DummyFile:
                     def __init__(self, d):
                         self.name = d.get('name', '')
                         self.extension = d.get('extension', '')
                         if not self.extension and '.' in self.name:
                             self.extension = self.name.split('.')[-1]
                         self.data = d.get('code') or d.get('data') or ''
                 
                 file_obj = DummyFile(f)
            else:
                 file_obj = f

            try:
                handler = FileHandlerFactory.get_handler(file_obj)
                lang = handler.get_language()
                
                # Check directly if it's a known language (not unknown)
                # We could expose a property "is_detected" on handler but checking against 'unknown' works
                # A manifest names a toolchain but is not itself source code, so it does not vote.
                if lang and lang != 'unknown' and not FileHandlerFactory.is_manifest(file_obj):
                    language_counts[lang] = language_counts.get(lang, 0) + 1
                    
                active_files.append((file_obj, handler))
                
            except Exception as e:
                logger.warning(f"Error detecting language for file {file_obj.name}: {e}")
                continue

        if not language_counts:
            return None

        detected_language_hint = max(language_counts, key=lambda k: language_counts[k])
        
        # Gather requirements from files matching the detected language
        blobs: List[str] = []
        uploaded: List[str] = []
        for file_obj, handler in active_files:
            try:
                if handler.get_language() == detected_language_hint:
                    reqs = handler.get_requirements()
                    if reqs:
                        (uploaded if FileHandlerFactory.is_manifest(file_obj) else blobs).append(reqs)
            except Exception:
                pass

        local_modules = Autodetector.collect_local_modules([f for f, _h in active_files])
        final_requirements = Autodetector.merge_requirements(detected_language_hint, blobs, local_modules, check_pypi, uploaded)

        return detected_language_hint, final_requirements

    @staticmethod
    def check_pypi_existence(package_name: str) -> bool:
        """
        Checks if a package exists on PyPI.
        """
        import requests
        from django.core.cache import cache
        cache_key = f"pypi-exists:{package_name}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            # Fast check using simple API or just HEAD request to /simple/
            # https://pypi.org/pypi/<package>/json is reliable
            url = f"https://pypi.org/pypi/{package_name}/json"
            response = requests.head(url, timeout=3)
            exists = response.status_code == 200
            if exists:
                logger.info(f"[AutoDetect] Package '{package_name}' verified on PyPI.")
            else:
                logger.info(f"[AutoDetect] Package '{package_name}' not found on PyPI (Status {response.status_code}).")
            cache.set(cache_key, exists, PYPI_CACHE_SECONDS)
            return exists
        except Exception as e:
            # Log the error but fail safe? 
            # If we really want to filter 'client', failing safe (returning True) defeats the purpose if network is bad.
            # But returning False might break valid packages if PyPI is down.
            # However, for this debugging session, let's see the error.
            logger.warning(f"[AutoDetect] PyPI check failed for '{package_name}': {e}. assuming True.")
            return True

    @staticmethod
    def detect_and_update(submission: Optional[Submission] = None, assignment: Optional["Assignment"] = None, force: bool = False,
                          check_pypi: bool = True) -> bool:
        """
        Analyzes ALL submission files for the assignment (and assignment files) and updates the environment.
        Can be run with just an assignment (scans assignment files only/mostly).
        """
        if submission:
            assignment = submission.assignment
        elif not assignment:
             logger.error("Autodetector called without submission or assignment")
             return False

        environment = assignment.environment
        
        if not environment or not environment.auto_detect:
            return False

        # Phase 1: Majority Vote for Language using DB stats
        # We can still use the fast DB aggregation for extensions, 
        # but now we need to map extensions to languages using our Factory/Handlers.
        # Ideally we don't instantiate handlers for every file in DB.
        # We can iterate the aggregation results and ask the Factory what language that extension maps to.
        
        stats = SubmissionFile.objects.filter(
            submission__assignment=assignment
        ).values('extension').annotate(count=Count('extension'))
        
        # If no submissions, we can't detect language from students. 
        # But we can try detecting from assignment files IF environment language is not set?
        # Or just skip language detection and do requirements scan if language is already set?
        
        # If stats is empty (no submissions), we skip successful language detection from students.
        # But we should still scan assignment files for requirements if language is known.
        
        language_counts: Dict[str, int] = {}
        ipynb_count = 0 
        _ipynb_extension = None

        if stats:
            # Build map from Extension -> Language using Factory logic
            # We instantiate a dummy file with that extension to check
            for entry in stats:
                ext = entry['extension']
                count = entry['count']
                
                # Dummy file for factory lookup
                class DummyFile:
                    def __init__(self, ext):
                        self.name = f"dummy.{ext}"
                        self.extension = ext
                        self.data = "" # No content
                
                if ext.lower().replace('.','') == 'ipynb':
                    ipynb_count += count
                    _ipynb_extension = ext
                    continue
                    
                try:
                    handler = FileHandlerFactory.get_handler(DummyFile(ext))
                    lang = handler.get_language()
                    if lang and lang != 'unknown':
                         language_counts[lang] = language_counts.get(lang, 0) + count
                except:
                    pass

        if not language_counts:
            # Fallback: Scan assignment files for language hints
            # This is slower but necessary if no submissions exist or if submissions yielded no language
            logger.info("[AutoDetect] No language detected from submissions (or none exist). Scanning assignment files.")
            for f in assignment.files.all():
                 if f.extension in NON_CODE_EXTENSIONS:
                     continue
                 try:
                     handler = FileHandlerFactory.get_handler(f)
                     lang = handler.get_language()
                     if lang and lang != 'unknown' and not FileHandlerFactory.is_manifest(f):
                         language_counts[lang] = language_counts.get(lang, 0) + 1
                         logger.info(f"[AutoDetect] Fallback: Detected {lang} from assignment file {f.name}")
                 except Exception as e:
                     logger.warning(f"[AutoDetect] Fallback error for {f.name}: {e}")

        # Notebook Sampling
        if ipynb_count > 0:
            sample_ids = list(SubmissionFile.objects.filter(
                submission__assignment=assignment, 
                extension__icontains='ipynb' 
            ).values_list('id', flat=True)[:100])
             
            import random
            if len(sample_ids) > 5:
                sample_ids = random.sample(sample_ids, 5)
                
            sample_files = SubmissionFile.objects.filter(id__in=sample_ids)
            
            detected_kernels = {}
            for f in sample_files:
                # Use the handler directly
                try:
                    lang = f.handler.get_language() 
                    if lang and lang != 'unknown':
                         detected_kernels[lang] = detected_kernels.get(lang, 0) + 1
                except:
                    pass
            
            if detected_kernels:
                dominant_kernel = max(detected_kernels, key=lambda k: detected_kernels[k])
                language_counts[dominant_kernel] = language_counts.get(dominant_kernel, 0) + ipynb_count

        detected_language_hint = None
        if language_counts:
            detected_language_hint = max(language_counts, key=lambda k: language_counts[k])
        elif environment.language:
             # Fallback to existing environment language if no submissions
             detected_language_hint = environment.language
        else:
             # No submissions and no env language -> cannot detect
             return False

        
        # Phase 2: Requirements scanning
        # We need to scan BOTH submission files and assignment files (instructor provided).
        # This ensures that:
        # 1. Instructor provided modules (e.g. client) are detected as local.
        # 2. Instructor provided requirements are included.
        
        all_files = []
        if submission:
            all_files.extend(list(submission.files.all()))
        
        all_files.extend(list(assignment.files.all()))

        # Include Test Scripts in scanning
        # This ensures libraries used in test scripts (e.g. pandas, numpy) are installed in the environment
        class ScriptDummyFile:
             def __init__(self, name, data):
                 self.name = name
                 self.extension = name.split('.')[-1]
                 self.data = data
                 self.path = ""

        for cat in assignment.testCategories.all():
            if cat.testScript and cat.testScript.strip():
                # We assume test scripts are Python for now as that's the primary script language
                # Using .py extension ensures the Python handler picks it up
                # TODO: Make sure the scripts have the right extension
                all_files.append(ScriptDummyFile(f"test_script_{cat.id}.py", cat.testScript))
        
        active_files = [f for f in all_files if f.extension not in NON_CODE_EXTENSIONS]
        local_modules = Autodetector.collect_local_modules(all_files)
        
        logger.info(f"[AutoDetect] Local modules identified: {local_modules}")

        # Detect requirements based on hint
        blobs: List[str] = []
        uploaded: List[str] = []
        for f in active_files:
             try:
                 # Use factory to get safe handler since we mixed SubmissionFile and AssignmentFile
                 handler = FileHandlerFactory.get_handler(f)
                 if handler.get_language() == detected_language_hint:
                     reqs = handler.get_requirements()
                     if reqs:
                         (uploaded if FileHandlerFactory.is_manifest(f) else blobs).append(reqs)
             except Exception as e:
                 logger.error(f"[AutoDetect] Error processing file {f.name}: {e}")

        final_requirements = Autodetector.merge_requirements(detected_language_hint, blobs, local_modules, check_pypi, uploaded)

        # Check against Environment
        if environment.build_status == 1 and not force: # Building
            logger.info(f"Auto-detect: Skipping update for Env {environment.id} because it is currently building.")
            return False
            
        updated = False
        if detected_language_hint and detected_language_hint != environment.language:
             environment.language = detected_language_hint
             updated = True
             
        new_reqs = final_requirements or ""
        current_reqs = environment.requirements or ""
        
        if new_reqs != current_reqs:
             environment.requirements = new_reqs
             logger.info(f"Auto-detect: Updated requirements for Env {environment.id} to '{new_reqs}'")
             updated = True

        if updated:
            environment.save()
            
            # Log Event
            try:
                meta = {
                    "event": "autodetect_update",
                    "environment_id": environment.id,
                    "language": environment.language,
                    "requirements_update": new_reqs != current_reqs,
                    "timestamp": time.time(),
                    "source": "submission" if submission else "assignment"
                }
                Event.objects.create(
                    category="autodetector",
                    user=str(submission.students.first()) if submission and submission.students.exists() else "system", 
                    description=f"Auto-detected update for Env {environment.id}: {environment.language}",
                    courseID=assignment.course.id if assignment else None,
                    meta=json.dumps(meta)
                )
            except Exception as e:
                logger.error(f"Failed to log autodetect event: {e}")

            
        return updated
