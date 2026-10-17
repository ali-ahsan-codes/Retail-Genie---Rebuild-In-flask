"""CSRF-protected authentication forms."""

from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, EqualTo, InputRequired, Length


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[InputRequired(), Length(max=48)])
    password = PasswordField("Password", validators=[InputRequired(), Length(max=128)])
    submit = SubmitField("Sign in")


class PasswordChangeForm(FlaskForm):
    current_password = PasswordField("Current password", validators=[InputRequired(), Length(max=128)])
    new_password = PasswordField("New password", validators=[InputRequired(), Length(min=12, max=128)])
    confirm_password = PasswordField(
        "Confirm new password",
        validators=[InputRequired(), EqualTo("new_password", message="The new passwords must match.")],
    )
    submit = SubmitField("Update password")
