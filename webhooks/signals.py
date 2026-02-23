# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from django.dispatch import Signal


hook_event = Signal()
hook_event.providing_args = ['action', 'instance']
raw_hook_event = Signal()
raw_hook_event.providing_args = ['event_name', 'payload', 'user']
hook_sent_event = Signal()
hook_sent_event.providing_args = ['payload', 'instance', 'hook']