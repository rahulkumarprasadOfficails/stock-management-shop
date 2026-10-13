from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _

from .models import CreditEntry, Customer, Invoice, Product, Shop, StockAdjustment, StockBatch

INPUT = "w-full rounded-xl border border-slate-300 px-4 py-3 text-base focus:border-teal-600 focus:outline-none"


class StyledForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", INPUT)


class LoginForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={"class": INPUT, "autocomplete": "username"}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"class": INPUT, "autocomplete": "current-password"}))


class ShopSetupForm(StyledForm):
    class Meta:
        model = Shop
        fields = ["name", "owner_name", "address", "phone", "gstin", "invoice_prefix", "invoice_type"]


class ProductForm(StyledForm):
    class Meta:
        model = Product
        fields = ["name", "unit", "selling_price", "purchase_price", "gst_percent", "hsn_code", "low_stock_limit"]

    def __init__(self, *args, shop=None, **kwargs):
        self.shop = shop
        super().__init__(*args, **kwargs)

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        qs = Product.objects.filter(shop=self.shop, name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(_("A product with this name already exists."))
        return name


class StockEntryForm(StyledForm):
    product = forms.ModelChoiceField(queryset=Product.objects.none())

    class Meta:
        model = StockBatch
        fields = ["product", "quantity_received", "expiry_date", "purchase_price", "note"]
        widgets = {"expiry_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, shop=None, **kwargs):
        self.shop = shop
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.filter(shop=shop, is_active=True)

    def save(self, commit=True):
        batch = super().save(commit=False)
        batch.shop = self.shop
        batch.quantity_remaining = batch.quantity_received
        if commit:
            batch.save()
        return batch


class ProductStockForm(forms.Form):
    name = forms.CharField(max_length=160, label=_("Product name"))
    unit = forms.ChoiceField(choices=Product.Unit.choices, label=_("Unit"))
    selling_price = forms.DecimalField(max_digits=12, decimal_places=2, min_value=0.01, label=_("Selling price"))
    purchase_price = forms.DecimalField(
        max_digits=12, decimal_places=2, min_value=0, required=False, label=_("Purchase price"),
    )
    gst_percent = forms.ChoiceField(
        choices=[(value, f"{value}%") for value in (0, 5, 12, 18, 28)], initial=0, label=_("GST"),
    )
    hsn_code = forms.CharField(max_length=20, required=False, label=_("HSN code"))
    low_stock_limit = forms.DecimalField(
        max_digits=12, decimal_places=3, min_value=0, initial=0, label=_("Low-stock limit"),
    )
    quantity_received = forms.DecimalField(
        max_digits=12, decimal_places=3, min_value=0.001, label=_("Opening quantity"),
    )
    expiry_date = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"}), label=_("Expiry date"),
    )
    note = forms.CharField(max_length=255, required=False, label=_("Note"))

    def __init__(self, *args, shop=None, **kwargs):
        self.shop = shop
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", INPUT)

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if Product.objects.filter(shop=self.shop, name__iexact=name).exists():
            raise forms.ValidationError(_("A product with this name already exists. Choose it in Add stock instead."))
        return name


class CustomerForm(StyledForm):
    class Meta:
        model = Customer
        fields = ["name", "whatsapp_number", "address", "is_promotion_allowed"]


class StaffForm(forms.Form):
    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"class": INPUT}))
    password = forms.CharField(min_length=10, widget=forms.PasswordInput(attrs={"class": INPUT}))

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError(_("This username is already in use."))
        return username


class CreditForm(forms.Form):
    entry_type = forms.ChoiceField(choices=CreditEntry.EntryType.choices)
    amount = forms.DecimalField(min_value=0.01, max_digits=12, decimal_places=2)
    note = forms.CharField(required=False, max_length=255)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", INPUT)


class CorrectionForm(forms.Form):
    direction = forms.ChoiceField(choices=[("REDUCE", _("Reduce quantity")), ("INCREASE", _("Increase quantity"))])
    quantity_change = forms.DecimalField(max_digits=12, decimal_places=3, min_value=0.001, label=_("Quantity"))
    reason = forms.ChoiceField(choices=StockAdjustment.Reason.choices)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", INPUT)


class PromotionForm(forms.Form):
    message = forms.CharField(max_length=1000, widget=forms.Textarea(attrs={"rows": 4, "class": INPUT}))


class BillingForm(forms.Form):
    customer = forms.ModelChoiceField(queryset=Customer.objects.none(), required=False)
    new_customer_name = forms.CharField(
        max_length=120, required=False, label=_("New customer name"),
    )
    new_customer_whatsapp_number = forms.CharField(
        max_length=10, required=False, label=_("WhatsApp number"),
    )
    new_customer_address = forms.CharField(
        required=False, label=_("Address"),
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    payment_type = forms.ChoiceField(choices=Invoice.PaymentType.choices)
    amount_paid = forms.DecimalField(min_value=0, max_digits=12, decimal_places=2, required=False, initial=0)
    items_json = forms.CharField(widget=forms.HiddenInput())

    def __init__(self, *args, shop=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = Customer.objects.filter(shop=shop)
        for field in self.fields.values():
            if not isinstance(field.widget, forms.HiddenInput):
                field.widget.attrs.setdefault("class", INPUT)

    def clean(self):
        cleaned = super().clean()
        name = (cleaned.get("new_customer_name") or "").strip()
        phone = (cleaned.get("new_customer_whatsapp_number") or "").strip()
        address = (cleaned.get("new_customer_address") or "").strip()
        entered_new_customer = bool(name or phone or address)
        if cleaned.get("customer") and entered_new_customer:
            raise forms.ValidationError(_("Choose an existing customer or enter a new customer, not both."))
        if entered_new_customer and not phone:
            self.add_error("new_customer_whatsapp_number", _("Enter a WhatsApp number for the new customer."))
        elif phone and (len(phone) != 10 or not phone.isdigit() or phone[0] not in "6789"):
            self.add_error("new_customer_whatsapp_number", _("Enter a valid 10-digit Indian mobile number."))
        if entered_new_customer and not name:
            self.add_error("new_customer_name", _("Enter the new customer's name."))
        cleaned["new_customer_name"] = name
        cleaned["new_customer_whatsapp_number"] = phone
        cleaned["new_customer_address"] = address
        return cleaned
