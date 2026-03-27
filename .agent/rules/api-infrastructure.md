---
trigger: always_on
glob:
description: Backend API patterns for codePost Django development
---

# codePost API Infrastructure Guide

## Tech Stack

Django 5.2 + Python 3.12 | DRF 3.16 | Celery 5.5 + Redis | MariaDB | Poetry | pytest + factory_boy

## virtual environments

Use ./.venv/ for Python virtual environment. Activate with `source .venv/bin/activate`. if available

## Project Layout

```
codePost-api/
├── codepost/           # Django settings, urls.py, wsgi.py
├── core/               # Main app: models, serializers/, views/, permissions/, tests/
├── autograder/         # run.py (Celery tasks), services/ (executors, builder)
├── webhooks/           # Webhook handling
└── util/               # Shared utilities
```

## Models (`core/models.py`)

All inherit `BaseModel` → provides `created`, `modified` fields.

**Hierarchy**:

```
Organization → Course → Assignment → Submission → Files/Comments
                      → TestCategory → TestCase
                      → RubricCategory → RubricComment
```

**File Types** (polymorphic): `SubmissionFile`, `AssignmentFile`, `CourseFile` all inherit `File`

### Model Pattern

```python
class MyModel(BaseModel):
    name = models.CharField(max_length=64, help_text="Description")

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name
```

## Serializers (`core/serializers/`)

Use `ModelSerializerWithPOSTCheck` for immutable fields after create:

```python
from core.serializers.template import ModelSerializerWithPOSTCheck

class MySerializer(ModelSerializerWithPOSTCheck):
    computed = serializers.SerializerMethodField()
    user = serializers.SlugRelatedField(slug_field='email', queryset=User.objects.all())

    class Meta:
        model = MyModel
        fields = ('id', 'name', 'computed', 'user')
        read_only_fields = ('id', 'computed')
        POST_permissions_fields = ('assignment',)  # Cannot change after POST
```

**Serializer Types**:

- `ModelSerializer` - Standard CRUD
- `AnonymousSerializer` - Hides student identities for grading
- `StudentSerializer` - Limited view for students

## Views (`core/views/`)

Standard `ModelViewSet` with role-based serializer switching:

```python
class MyViewSet(viewsets.ModelViewSet):
    queryset = MyModel.objects.all()
    serializer_class = MySerializer
    permission_classes = [MyPermissions]

    def get_serializer_class(self):
        if isStudent(self.request.user, course):
            return StudentSerializer
        return MySerializer

    @action(detail=True, methods=['post'])
    def custom_action(self, request, pk=None):
        obj = self.get_object()
        return Response({'status': 'done'})
```

## Permissions (`core/permissions/`)

Inherit `TemplatePermission`. Pattern:

```python
from core.permissions.template import TemplatePermission
from core.permissions.helpers import isCourseAdmin, isCourseStaff, isStaffOfSub

class MyPermissions(TemplatePermission):
    def has_object_permission(self, request, view, obj):
        if request.method == "DELETE":
            return False  # Use admin console
        if request.method == "GET":
            return isCourseStaff(request.user, obj.course)
        return isCourseAdmin(request.user, obj.course)
```

**Helper Functions**:
| Helper | Description |
|--------|-------------|
| `isCourseAdmin(user, course)` | User is course administrator |
| `isCourseStaff(user, course)` | User is grader or admin |
| `isCourseMember(user, course)` | User has any role in course |
| `isStudent(user, course)` | User is student in course |
| `isStaffOfSub(user, sub)` | User is grader assigned to submission |
| `isStudentOfSub(user, sub)` | User is student on submission |

## Celery Tasks (`autograder/run.py`)

```python
from celery import shared_task
from autograder.celery import app, logger

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def RunSubmission(self, submissionID):
    try:
        # Execute and cache submission files
        return {"success": True}
    except Exception as e:
        raise self.retry(exc=e)

# Trigger async
RunSubmission.delay(submission_id)
```

**Key Tasks**:

- `RunSubmission` - Execute/cache submission files
- `BuildEnvironment` - Build Docker image for autograder
- `RunAll` - Run all tests on all submissions
- `CleanupOldImages` - Remove old Docker images

## Testing (`core/tests/`)

Use `factory_boy` with muted signals:

```python
import factory
from django.db.models.signals import post_save

@factory.django.mute_signals(post_save)
class CourseFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Course
        django_get_or_create = ('name', 'period', 'organization')

    name = "cs101"
    period = "s2020"
    organization = factory.SubFactory(OrganizationFactory)
```

**Test Structure**:

```
core/tests/
├── factories.py      # All factory definitions
├── models/           # Model unit tests
├── serializers/      # Serializer tests
└── views/            # API integration tests
```

## URL Configuration (`codepost/urls.py`)

```python
router = routers.DefaultRouter()
router.register(r'courses', CourseViewSet)
router.register(r'submissions', SubmissionViewSet)
# ... etc

urlpatterns = [
    path('admin/', admin.site.urls),
    path('token-auth/', obtain_jwt_token),
    re_path('', include(router.urls)),
]
```

## Commands

```bash
poetry install                          # Install deps
./init.sh python manage.py runserver   # Dev server
python manage.py migrate                # Run migrations
pytest                                  # Run tests
pytest --cov=core                       # With coverage
celery -A autograder worker -l info     # Start worker
python manage.py spectacular --schema schema.yaml  # Generate OpenAPI
```

## Important Notes

1. **Signals**: Profile auto-created on User save (`core/signals.py`)
2. **DELETE Disabled**: Most DELETE apis blocked - use Django admin console
3. **Encryption**: Sensitive fields use `django-encrypted-model-fields`
4. **Logging**: Use `from codepost.settings import logger`
5. **Type Checking**: Run `pyright` before committing
6. **API Docs**: Available at `/api/schema/swagger-ui/`
