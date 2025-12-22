import re
from django.core.exceptions import ValidationError


def validate_hex_color(value: str):
    is_valid = re.search(r"^#(?:[0-9a-fA-F]{3}){1,2}$", value)
    if not is_valid:
        raise ValidationError(
            '{} is not a a valid hexadecimal color'.format(value)
        )