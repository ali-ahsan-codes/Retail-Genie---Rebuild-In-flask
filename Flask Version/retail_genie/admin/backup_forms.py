"""Input validation for automatic database backup settings."""

from flask_wtf import FlaskForm
from wtforms import BooleanField, IntegerField, SubmitField
from wtforms.validators import InputRequired, NumberRange


class BackupSettingsForm(FlaskForm):
    enabled = BooleanField("Enable automatic backups")
    interval_minutes = IntegerField(
        "Run every (minutes)",
        validators=[InputRequired(), NumberRange(min=15, max=10080)],
    )
    retention_count = IntegerField(
        "Keep the most recent backup files",
        validators=[InputRequired(), NumberRange(min=1, max=365)],
    )
    submit = SubmitField("Save backup schedule")
