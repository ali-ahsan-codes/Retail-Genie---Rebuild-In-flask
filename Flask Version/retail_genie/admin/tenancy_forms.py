"""Forms for company, store, and store-assignment administration."""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask_wtf import FlaskForm
from wtforms import BooleanField, IntegerField, PasswordField, SelectField, SelectMultipleField, StringField, SubmitField
from wtforms.validators import InputRequired, Length, NumberRange, Optional, Regexp, ValidationError


class CreateCompanyForm(FlaskForm):
    company_name = StringField("Company name", validators=[InputRequired(), Length(min=2, max=160)])
    slug = StringField(
        "Company code",
        validators=[InputRequired(), Length(min=3, max=64), Regexp(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")],
    )
    timezone = StringField("Timezone", default="Asia/Muscat", validators=[InputRequired(), Length(max=64)])
    store_name = StringField("First store name", validators=[InputRequired(), Length(min=2, max=160)])

    def validate_timezone(self, field):
        try:
            ZoneInfo((field.data or "").strip())
        except (ZoneInfoNotFoundError, TypeError, ValueError):
            raise ValidationError("Use a valid IANA timezone, such as Asia/Muscat.") from None
    store_code = StringField(
        "First store code",
        validators=[InputRequired(), Length(min=1, max=48), Regexp(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")],
    )
    admin_username = StringField(
        "Company Admin username",
        validators=[InputRequired(), Length(min=3, max=48), Regexp(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,47}$")],
    )
    admin_password = PasswordField("Temporary password", validators=[InputRequired(), Length(min=12, max=128)])
    submit = SubmitField("Create company")


class StoreForm(FlaskForm):
    name = StringField("Store name", validators=[InputRequired(), Length(min=2, max=160)])
    code = StringField("Store code", validators=[InputRequired(), Length(min=1, max=48), Regexp(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")])
    submit = SubmitField("Add store")


class AssignmentForm(FlaskForm):
    company_id = SelectField("Company", choices=[])
    user_id = SelectField("Manager or staff account", choices=[], validators=[InputRequired()])
    store_id = SelectField("Store", choices=[], validators=[InputRequired()])
    can_view_shared_bills = BooleanField("Allow limited cross-store open-bill lookup (Super Admin only)")
    submit = SubmitField("Save assignment")


class DomainPolicyForm(FlaskForm):
    is_enabled = BooleanField("Enable this data domain", default=True)
    sharing_mode = SelectField(
        "Sharing scope",
        choices=[],
        validators=[InputRequired()],
    )
    allow_company_ids = SelectMultipleField("Allow these companies", choices=[], validators=[Optional()])
    deny_company_ids = SelectMultipleField("Explicitly deny these companies", choices=[], validators=[Optional()])
    allow_store_ids = SelectMultipleField("Allow these stores", choices=[], validators=[Optional()])
    deny_store_ids = SelectMultipleField("Explicitly deny these stores", choices=[], validators=[Optional()])
    submit = SubmitField("Save policy")


class BillingSettingsForm(FlaskForm):
    mixed_tender_category = SelectField(
        "Invoice category for mixed tender",
        choices=[("cash", "Cash"), ("bank", "Bank"), ("bank_transfer", "Bank Transfer"), ("other", "Other")],
        validators=[InputRequired()],
    )
    cash_prefix = StringField("Cash prefix", validators=[InputRequired(), Length(max=16), Regexp(r"^[A-Z0-9][A-Z0-9_-]{0,15}$")])
    cash_next_number = IntegerField("Next Cash number", validators=[InputRequired(), NumberRange(min=1, max=999999999)])
    bank_prefix = StringField("Bank prefix", validators=[InputRequired(), Length(max=16), Regexp(r"^[A-Z0-9][A-Z0-9_-]{0,15}$")])
    bank_next_number = IntegerField("Next Bank number", validators=[InputRequired(), NumberRange(min=1, max=999999999)])
    bank_transfer_prefix = StringField("Bank Transfer prefix", validators=[InputRequired(), Length(max=16), Regexp(r"^[A-Z0-9][A-Z0-9_-]{0,15}$")])
    bank_transfer_next_number = IntegerField("Next Bank Transfer number", validators=[InputRequired(), NumberRange(min=1, max=999999999)])
    other_prefix = StringField("Other prefix", validators=[InputRequired(), Length(max=16), Regexp(r"^[A-Z0-9][A-Z0-9_-]{0,15}$")])
    other_next_number = IntegerField("Next Other number", validators=[InputRequired(), NumberRange(min=1, max=999999999)])
    submit = SubmitField("Save billing setup")
