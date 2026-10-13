import secrets
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Sum
from django.utils.translation import gettext_lazy as _


def generate_share_token():
    return secrets.token_urlsafe(24)


class Shop(models.Model):
    class InvoiceType(models.TextChoices):
        TAX_INVOICE = "TAX_INVOICE", _("Tax invoice")
        BILL_OF_SUPPLY = "BILL_OF_SUPPLY", _("Bill of supply")

    name = models.CharField(max_length=160)
    owner_name = models.CharField(max_length=120, blank=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=10, blank=True, validators=[RegexValidator(r"^[6-9]\d{9}$", _("Enter a valid 10-digit Indian mobile number."))])
    gstin = models.CharField(max_length=15, blank=True, validators=[RegexValidator(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$", _("Enter a valid GSTIN."))])
    invoice_prefix = models.CharField(max_length=12, default="INV")
    invoice_type = models.CharField(max_length=20, choices=InvoiceType.choices, default=InvoiceType.TAX_INVOICE)
    is_active = models.BooleanField(default=True)
    valid_until = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_invoice_number = models.PositiveIntegerField(default=0)
    setup_completed = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class ShopQuerySet(models.QuerySet):
    def for_user(self, user):
        if not user.is_authenticated or user.is_superuser:
            return self.none()
        try:
            shop_id = user.profile.shop_id
        except UserProfile.DoesNotExist:
            return self.none()
        return self.filter(shop_id=shop_id)


class ShopOwnedModel(models.Model):
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE)
    objects = ShopQuerySet.as_manager()

    class Meta:
        abstract = True


class UserProfile(models.Model):
    class Role(models.TextChoices):
        OWNER = "OWNER", _("Owner")
        STAFF = "STAFF", _("Staff")

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="profiles")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.OWNER)
    must_change_password = models.BooleanField(default=True)
    objects = ShopQuerySet.as_manager()

    def __str__(self):
        return f"{self.user.username} ({self.shop})"


class Announcement(models.Model):
    title = models.CharField(max_length=160)
    message = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    targeted_shops = models.ManyToManyField(
        Shop, through="AnnouncementTarget", related_name="targeted_announcements", blank=True,
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class AnnouncementTarget(models.Model):
    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE)
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["announcement", "shop"], name="unique_announcement_shop_target"),
        ]


class Product(ShopOwnedModel):
    class Unit(models.TextChoices):
        PCS = "pcs", _("pcs")
        KG = "kg", _("kg")
        G = "g", _("g")
        LITRE = "litre", _("litre")
        ML = "ml", _("ml")
        PACKET = "packet", _("packet")
        BOX = "box", _("box")

    name = models.CharField(max_length=160)
    unit = models.CharField(max_length=10, choices=Unit.choices, default=Unit.PCS)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    purchase_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal("0.00"))])
    gst_percent = models.PositiveSmallIntegerField(choices=[(x, f"{x}%") for x in (0, 5, 12, 18, 28)], default=0)
    hsn_code = models.CharField(max_length=20, blank=True)
    low_stock_limit = models.DecimalField(max_digits=12, decimal_places=3, default=0, validators=[MinValueValidator(Decimal("0"))])
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["shop", "name"], name="unique_product_name_per_shop")]
        indexes = [models.Index(fields=["shop", "name"]), models.Index(fields=["shop", "is_active"])]

    @property
    def stock_quantity(self):
        return self.batches.filter(shop_id=self.shop_id).aggregate(total=Sum("quantity_remaining"))["total"] or Decimal("0")

    def __str__(self):
        return self.name


class StockBatch(ShopOwnedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="batches")
    quantity_received = models.DecimalField(max_digits=12, decimal_places=3, validators=[MinValueValidator(Decimal("0.001"))])
    quantity_remaining = models.DecimalField(max_digits=12, decimal_places=3, validators=[MinValueValidator(Decimal("0"))])
    expiry_date = models.DateField(null=True, blank=True)
    purchase_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal("0"))])
    received_on = models.DateField(auto_now_add=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["expiry_date", "received_on", "id"]
        indexes = [models.Index(fields=["shop", "expiry_date"]), models.Index(fields=["shop", "product"])]


class StockAdjustment(ShopOwnedModel):
    class Reason(models.TextChoices):
        DAMAGED = "DAMAGED", _("Damaged")
        EXPIRED = "EXPIRED", _("Expired")
        LOST = "LOST", _("Lost")
        CORRECTION = "CORRECTION", _("Correction")
        RETURN = "RETURN", _("Return")

    batch = models.ForeignKey(StockBatch, on_delete=models.PROTECT, related_name="adjustments")
    quantity_change = models.DecimalField(max_digits=12, decimal_places=3)
    reason = models.CharField(max_length=12, choices=Reason.choices)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class Customer(ShopOwnedModel):
    name = models.CharField(max_length=120)
    whatsapp_number = models.CharField(max_length=10, validators=[RegexValidator(r"^[6-9]\d{9}$", _("Enter a valid 10-digit Indian mobile number."))])
    address = models.TextField(blank=True)
    is_promotion_allowed = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["shop", "name"]), models.Index(fields=["shop", "whatsapp_number"])]

    def __str__(self):
        return self.name

    @property
    def whatsapp_international(self):
        return f"91{self.whatsapp_number}"


class Invoice(ShopOwnedModel):
    class PaymentType(models.TextChoices):
        CASH = "CASH", _("Cash")
        UPI = "UPI", _("UPI")
        CREDIT = "CREDIT", _("Credit")

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", _("Active")
        CANCELLED = "CANCELLED", _("Cancelled")

    number = models.CharField(max_length=40)
    share_token = models.CharField(max_length=48, unique=True, default=generate_share_token, editable=False)
    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.SET_NULL, related_name="invoices")
    date = models.DateTimeField(auto_now_add=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_type = models.CharField(max_length=10, choices=PaymentType.choices, default=PaymentType.CASH)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["shop", "number"], name="unique_invoice_number_per_shop")]
        indexes = [models.Index(fields=["shop", "date"]), models.Index(fields=["shop", "status"])]
        ordering = ["-date"]


class InvoiceItem(ShopOwnedModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    gst_percent = models.PositiveSmallIntegerField(default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)


class InvoiceItemBatch(ShopOwnedModel):
    invoice_item = models.ForeignKey(InvoiceItem, on_delete=models.CASCADE, related_name="batch_allocations")
    batch = models.ForeignKey(StockBatch, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)


class CreditEntry(ShopOwnedModel):
    class EntryType(models.TextChoices):
        GIVEN = "GIVEN", _("Credit given")
        RECEIVED = "RECEIVED", _("Payment received")

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="credit_entries")
    entry_type = models.CharField(max_length=10, choices=EntryType.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    invoice = models.ForeignKey(Invoice, null=True, blank=True, on_delete=models.SET_NULL, related_name="credit_entries")
    date = models.DateField(auto_now_add=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-date", "-id"]
        indexes = [models.Index(fields=["shop", "customer", "date"])]


class PromotionLog(ShopOwnedModel):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="promotion_logs")
    message = models.TextField()
    sent_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-sent_on"]
        indexes = [models.Index(fields=["shop", "customer", "sent_on"])]
