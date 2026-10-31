"""Forms for platform plan administration and tenant subscription requests."""

from decimal import Decimal, InvalidOperation

from flask_wtf import FlaskForm
from wtforms import BooleanField, IntegerField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import InputRequired, Length, NumberRange, Optional, Regexp, ValidationError

from ..models.saas import SUBSCRIPTION_STATUSES


class SubscriptionPlanForm(FlaskForm):
    code = StringField(
        "Plan code",
        validators=[InputRequired(), Length(min=2, max=40), Regexp(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")],
    )
    name = StringField("Display name", validators=[InputRequired(), Length(min=2, max=100)])
    description = StringField("Description", validators=[Optional(), Length(max=500)])
    monthly_price = StringField("Monthly price (OMR)", validators=[InputRequired(), Length(max=16)])
    max_companies = IntegerField("Companies (blank = unlimited)", validators=[Optional(), NumberRange(min=1, max=100000)])
    max_stores = IntegerField("Stores (blank = unlimited)", validators=[Optional(), NumberRange(min=1, max=100000)])
    max_active_users = IntegerField("Active users (blank = unlimited)", validators=[Optional(), NumberRange(min=1, max=100000)])
    features = StringField("Included feature labels (comma-separated)", validators=[Optional(), Length(max=1000)])
    sort_order = IntegerField("Display order", default=100, validators=[InputRequired(), NumberRange(min=0, max=100000)])
    is_active = BooleanField("Available for new assignments", default=True)
    submit = SubmitField("Create plan")

    def validate_monthly_price(self, field):
        try:
            amount = Decimal((field.data or "").strip())
        except (InvalidOperation, AttributeError):
            raise ValidationError("Enter a valid OMR amount with at most three decimals.") from None
        if not amount.is_finite() or amount < 0 or amount.as_tuple().exponent < -3 or amount > Decimal("999999999.999"):
            raise ValidationError("Price must be non-negative and have at most three decimal places.")
        field.data = amount


class TenantSubscriptionForm(FlaskForm):
    plan_id = SelectField("Plan", choices=[], validators=[InputRequired()])
    status = SelectField(
        "Subscription status",
        choices=[(status, status.replace("_", " ").title()) for status in SUBSCRIPTION_STATUSES],
        validators=[InputRequired()],
    )
    internal_note = TextAreaField("Internal billing note", validators=[Optional(), Length(max=2000)])
    submit = SubmitField("Save subscription")


class PlanChangeRequestForm(FlaskForm):
    plan_id = SelectField("Requested plan", choices=[], validators=[InputRequired()])
    note = StringField("Note for the Main Admin (optional)", validators=[Optional(), Length(max=500)])
    submit = SubmitField("Request plan change")


class ReviewPlanRequestForm(FlaskForm):
    decision = SelectField("Decision", choices=[("approve", "Approve"), ("reject", "Reject")], validators=[InputRequired()])
    review_note = StringField("Review note (optional)", validators=[Optional(), Length(max=500)])
    submit = SubmitField("Review request")
