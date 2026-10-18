"""CSRF-protected forms for catalog and inventory screens."""

from flask_wtf import FlaskForm
from wtforms import BooleanField, DecimalField, IntegerField, SelectField, StringField, SubmitField
from wtforms.validators import InputRequired, Length, NumberRange, Optional


class ProductForm(FlaskForm):
    store_id = SelectField("Company / store", choices=[], validators=[InputRequired()])
    name = StringField("Product name", validators=[InputRequired(), Length(max=255)])
    sku = StringField("SKU", validators=[Optional(), Length(max=128)])
    barcode = StringField("Barcode", validators=[Optional(), Length(max=128)])
    category = StringField("Category", validators=[Optional(), Length(max=128)])
    price = DecimalField("Unit price (OMR)", places=3, validators=[Optional(), NumberRange(min=0, max=99999999999.999)])
    low_stock_price = DecimalField("Low-stock price (OMR)", places=3, validators=[Optional(), NumberRange(min=0, max=99999999999.999)])
    expiry_date = StringField("Expiry date", validators=[Optional(), Length(max=40)])
    low_stock_threshold = IntegerField("Low-stock alert at", validators=[Optional(), NumberRange(min=0, max=2147483647)])
    is_demand_notice_product = BooleanField("Use in demand notices")
    submit = SubmitField("Add product")


class InventoryAdjustmentForm(FlaskForm):
    store_id = StringField(validators=[InputRequired(), Length(max=64)])
    delta = IntegerField("Quantity change", validators=[InputRequired(), NumberRange(min=-2147483647, max=2147483647)])
    reason = StringField("Reason", validators=[InputRequired(), Length(min=1, max=500)])
    submit = SubmitField("Update stock")
