import re

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import Announcement, Shop, ShopkeeperUser


GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
PHONE_RE = re.compile(r"^[6-9]\d{9}$")


class ControlLoginForm(AuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not (user.is_superuser or user.is_staff):
            raise ValidationError("This account cannot access the control panel.")


class ShopCreateForm(forms.Form):
    name = forms.CharField(max_length=160)
    owner_name = forms.CharField(max_length=120)
    phone = forms.CharField(max_length=10)
    address = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
    gstin = forms.CharField(max_length=15, required=False)
    invoice_prefix = forms.CharField(max_length=12, initial="INV")
    invoice_type = forms.ChoiceField(choices=(("TAX_INVOICE", "Tax invoice"), ("BILL_OF_SUPPLY", "Bill of supply")))
    username = forms.CharField(max_length=150)

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        if not PHONE_RE.fullmatch(phone):
            raise ValidationError("Enter a valid 10-digit Indian mobile number.")
        return phone

    def clean_gstin(self):
        gstin = self.cleaned_data["gstin"].strip().upper()
        if gstin and not GSTIN_RE.fullmatch(gstin):
            raise ValidationError("Enter a valid GSTIN.")
        return gstin

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        UnicodeUsernameValidator()(username)
        if ShopkeeperUser.objects.filter(username__iexact=username).exists():
            raise ValidationError("That username already exists in the ShopKeeper app.")
        return username


class ShopEditForm(forms.ModelForm):
    class Meta:
        model = Shop
        fields = ("name", "owner_name", "address", "phone", "gstin", "invoice_prefix", "invoice_type")

    def clean_phone(self):
        value = self.cleaned_data["phone"].strip()
        if value and not PHONE_RE.fullmatch(value):
            raise ValidationError("Enter a valid 10-digit Indian mobile number.")
        return value

    def clean_gstin(self):
        value = self.cleaned_data["gstin"].strip().upper()
        if value and not GSTIN_RE.fullmatch(value):
            raise ValidationError("Enter a valid GSTIN.")
        return value


class AnnouncementForm(forms.ModelForm):
    targeted_shops = forms.ModelMultipleChoiceField(
        queryset=Shop.objects.all(), required=False,
        widget=forms.SelectMultiple(attrs={"size": 6}),
        help_text="Leave empty to show this announcement to every shop.",
    )

    class Meta:
        model = Announcement
        fields = ("title", "message", "is_active", "starts_at", "ends_at", "targeted_shops")
        widgets = {
            "starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def clean(self):
        cleaned = super().clean()
        starts_at = cleaned.get("starts_at")
        ends_at = cleaned.get("ends_at")
        if starts_at and timezone.is_naive(starts_at):
            cleaned["starts_at"] = timezone.make_aware(starts_at)
        if ends_at and timezone.is_naive(ends_at):
            cleaned["ends_at"] = timezone.make_aware(ends_at)
        if starts_at and ends_at and starts_at >= ends_at:
            self.add_error("ends_at", "End date must be after the start date.")
        return cleaned


class StockFixForm(forms.Form):
    quantity_remaining = forms.DecimalField(min_value=0, max_digits=12, decimal_places=3)
    reason = forms.CharField(max_length=255)


class ValidUntilForm(forms.Form):
    valid_until = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
