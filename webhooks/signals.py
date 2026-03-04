# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from django.dispatch import Signal


hook_event = Signal()       # provides: action, instance
raw_hook_event = Signal()   # provides: event_name, payload, user
hook_sent_event = Signal()  # provides: payload, instance, hook