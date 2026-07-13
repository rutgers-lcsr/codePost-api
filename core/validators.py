# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
import re
from django.core.exceptions import ValidationError


def validate_hex_color(value: str):
    is_valid = re.search(r"^#(?:[0-9a-fA-F]{3}){1,2}$", value)
    if not is_valid:
        raise ValidationError(
            '{} is not a a valid hexadecimal color'.format(value)
        )