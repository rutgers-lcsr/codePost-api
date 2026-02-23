# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
import django

try:
    from django.apps import apps as django_apps
except ImportError:
    django_apps = None
from django.core.exceptions import ImproperlyConfigured
from django.conf import settings

if django.VERSION >= (2, 0,):
    get_model_kwargs = {'require_ready': False}
else:
    get_model_kwargs = {}


def get_module(path):
    """
    A modified duplicate from Django's built in backend
    retriever.

        slugify = get_module('django.template.defaultfilters.slugify')
    """
    try:
        from importlib import import_module
    except ImportError as e:
        from django.utils.importlib import import_module

    try:
        mod_name, func_name = path.rsplit('.', 1)
        mod = import_module(mod_name)
    except ImportError as e:
        raise ImportError(
            'Error importing alert function {0}: "{1}"'.format(mod_name, e))

    try:
        func = getattr(mod, func_name)
    except AttributeError:
        raise ImportError(
            ('Module "{0}" does not define a "{1}" function'
             ).format(mod_name, func_name))

    return func


def get_hook_model():
    """
    Returns the Custom Hook model if defined in settings,
    otherwise the default Hook model.
    """
    model_label = getattr(settings, 'HOOK_CUSTOM_MODEL', None)
    if django_apps:
        model_label = (model_label or 'webhooks.Hook').replace('.models.', '.')
        try:
            return django_apps.get_model(model_label, **get_model_kwargs)
        except ValueError:
            raise ImproperlyConfigured("HOOK_CUSTOM_MODEL must be of the form 'app_label.model_name'")
        except LookupError:
            raise ImproperlyConfigured(
                "HOOK_CUSTOM_MODEL refers to model '%s' that has not been installed" % model_label
            )
    else:
        if model_label in (None, 'webhooks.Hook'):
            from webhooks.models import Hook
            HookModel = Hook
        else:
            try:
                HookModel = get_module(settings.HOOK_CUSTOM_MODEL)
            except ImportError:
                raise ImproperlyConfigured(
                    "HOOK_CUSTOM_MODEL refers to model '%s' that cannot be imported" % model_label
                )
        return HookModel


def find_and_fire_hook(event_name, instance, user_override=None, payload_override=None, updated_fields=[], payload_addition=None):
    """
    Look up Hooks that apply
    """
    from django.contrib.auth.models import User
    from webhooks.models import HOOK_EVENTS

    if event_name not in HOOK_EVENTS.keys():
        raise Exception(
            '"{}" does not exist in `settings.HOOK_EVENTS`.'.format(event_name)
        )

    filters = {'event': event_name, 'is_active': True}

    ##############################################################################
    # codePost webhooks are currently only defined at the course-level.
    #
    # If we want to create hooks for other objects that don't have a unique course
    # (e.g. User, Organization, Profile... )
    # or define webhooks at a non-course level
    # (e.g. Submission)
    # then we need to update this method.
    ##############################################################################
    try:
        related_course = instance.course
    except AttributeError:
        raise Exception('{} has no related `course` property.'.format(repr(instance)))

    # If the course is None (e.g., during cascade deletion), skip webhook delivery
    if related_course is None:
        return

    filters['course'] = related_course.id

    HookModel = get_hook_model()
    hooks = HookModel.objects.filter(**filters)


    for hook in hooks:
        hook.deliver_hook(instance, payload_override=payload_override, updated_fields=updated_fields, payload_addition=payload_addition)


def distill_model_event(
        instance,
        model=False,
        action=False,
        user_override=None,
        event_name=False,
        trust_event_name=False,
        payload_override=None,
        updated_fields=None,
        payload_addition=None
):
    """
    Take `event_name` or determine it using action and model
    from settings.HOOK_EVENTS, and let hooks fly.

    if `event_name` is passed together with `model` or `action`, then
    they should be the same as in settings or `trust_event_name` should be
    `True`

    If event_name is not found or is invalidated, then just quit silently.

    If payload_override is passed, then it will be passed into HookModel.deliver_hook

    """
    from webhooks.models import get_event_actions_config, HOOK_EVENTS

    if event_name is False and (model is False or action is False):
        raise TypeError(
            'distill_model_event() requires either `event_name` argument or '
            'both `model` and `action` arguments.'
        )
    if event_name:
        if trust_event_name:
            pass
        elif event_name in HOOK_EVENTS:
            auto = HOOK_EVENTS[event_name]
            if auto:
                allowed_model, allowed_action = auto.rsplit('.', 1)

                allowed_action_parts = allowed_action.rsplit('+', 1)
                allowed_action = allowed_action_parts[0]

                model = model or allowed_model
                action = action or allowed_action

                if not (model == allowed_model and action == allowed_action):
                    event_name = None

                if len(allowed_action_parts) == 2:
                    user_override = False
    else:

        if updated_fields is not None:
            """
            *** This is the path codePost will go down most of the time.
            We preserve the other conditional routes in order to preserve
            other webhook functionality offered by the original package but
            not yet necessary for us.
            """
            event_actions_config = get_event_actions_config()
            event_name, ignore_user_override = event_actions_config.get(model, {}).get(action, (None, False))

            if event_name:
                ''' Created / Updated / Deleted Hook '''
                if getattr(settings, 'HOOK_FINDER', None):
                    finder = get_module(settings.HOOK_FINDER)
                else:
                    finder = find_and_fire_hook

                # FIXME:
                # This is a bit of a weak solution to the unwanted webhook triggers.
                # Here's the base example:
                # You update a comment's text. So Submission.dateEdited gets updated.
                # So the Submission.changed webhook triggers.
                #
                # This conditional prevents it from firing, but it's up for discussion
                # whether this is the desired behavior.
                from webhooks.codepost_hooks import ignored_fields
                if model in ignored_fields and list(updated_fields) == ignored_fields[model]:
                    pass
                else:
                    finder(event_name, instance, user_override=user_override,
                           payload_override=payload_override, updated_fields=updated_fields, payload_addition=payload_addition)

            for updated_field in updated_fields:
                ''' Field Update Hooks '''
                event_name, ignore_user_override = event_actions_config.get(model, {}).get(updated_field, (None, False))

                if event_name:
                    if getattr(settings, 'HOOK_FINDER', None):
                        finder = get_module(settings.HOOK_FINDER)
                    else:
                        finder = find_and_fire_hook

                    finder(event_name, instance, user_override=user_override,
                           payload_override=payload_override, updated_fields=updated_fields, payload_addition=payload_addition)

            return

        event_actions_config = get_event_actions_config()
        event_name, ignore_user_override = event_actions_config.get(model, {}).get(action, (None, False))
        if ignore_user_override:
            user_override = False

    if event_name:
        if getattr(settings, 'HOOK_FINDER', None):
            finder = get_module(settings.HOOK_FINDER)
        else:
            finder = find_and_fire_hook
        finder(event_name, instance, user_override=user_override, payload_override=payload_override)

