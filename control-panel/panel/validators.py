from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class PasswordComplexityValidator:
    def validate(self, password, user=None):
        requirements = (
            any(char.islower() for char in password),
            any(char.isupper() for char in password),
            any(char.isdigit() for char in password),
            any(not char.isalnum() for char in password),
        )
        if not all(requirements):
            raise ValidationError(
                _("Use at least one lowercase letter, uppercase letter, number, and symbol."),
                code="password_complexity",
            )

    def get_help_text(self):
        return _("Use at least one lowercase letter, uppercase letter, number, and symbol.")
