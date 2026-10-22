"""Forms for centrally managed user accounts."""

from flask_wtf import FlaskForm
from wtforms import PasswordField, SelectField, SelectMultipleField, StringField, SubmitField
from wtforms.validators import InputRequired, Length, Optional, Regexp, ValidationError

from ..models import is_valid_username


class CreateUserForm(FlaskForm):
    company_id = SelectField("Company", choices=[], validators=[Optional()])
    username = StringField(
        "Username",
        validators=[
            InputRequired(),
            Length(min=3, max=48),
            Regexp(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,47}$", message="Use letters, numbers, dots, underscores, or hyphens."),
        ],
    )
    role = SelectField("Role", choices=[], validators=[InputRequired()])
    password = PasswordField("Temporary password", validators=[InputRequired(), Length(min=12, max=128)])
    permissions = SelectMultipleField("Permissions", choices=[], validators=[Optional()])
    submit = SubmitField("Create account")

    def validate_username(self, field):
        if not is_valid_username(field.data or ""):
            raise ValidationError("Use 3–48 characters: letters, numbers, dots, underscores, or hyphens.")
