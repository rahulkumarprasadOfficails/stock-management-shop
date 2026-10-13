from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class AdminUser(AbstractUser):
    class Meta:
        db_table = "control_adminuser"


class AuditLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=80, db_index=True)
    object_type = models.CharField(max_length=80, blank=True)
    object_id = models.CharField(max_length=80, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} by {self.actor}"


class Shop(models.Model):
    name = models.CharField(max_length=160)
    owner_name = models.CharField(max_length=120, blank=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=10, blank=True)
    gstin = models.CharField(max_length=15, blank=True)
    invoice_prefix = models.CharField(max_length=12, default="INV")
    invoice_type = models.CharField(
        max_length=20, default="TAX_INVOICE",
        choices=(("TAX_INVOICE", "Tax invoice"), ("BILL_OF_SUPPLY", "Bill of supply")),
    )
    is_active = models.BooleanField(default=True)
    valid_until = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField()
    last_invoice_number = models.PositiveIntegerField(default=0)
    setup_completed = models.BooleanField(default=False)

    class Meta:
        managed = False
        db_table = "store_shop"
        ordering = ["name"]


class ShopkeeperUser(models.Model):
    password = models.CharField(max_length=128)
    last_login = models.DateTimeField(null=True, blank=True)
    is_superuser = models.BooleanField(default=False)
    username = models.CharField(max_length=150, unique=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    email = models.CharField(max_length=254, blank=True)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "auth_user"


class UserProfile(models.Model):
    user = models.OneToOneField(ShopkeeperUser, models.DO_NOTHING, related_name="shop_profile")
    shop = models.ForeignKey(Shop, models.DO_NOTHING, related_name="profiles")
    role = models.CharField(max_length=10, default="OWNER")
    must_change_password = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "store_userprofile"


class Product(models.Model):
    shop = models.ForeignKey(Shop, models.DO_NOTHING)
    name = models.CharField(max_length=160)
    unit = models.CharField(max_length=10)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2)
    purchase_price = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    gst_percent = models.PositiveSmallIntegerField(default=0)
    hsn_code = models.CharField(max_length=20, blank=True)
    low_stock_limit = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "store_product"
        ordering = ["name"]


class StockBatch(models.Model):
    shop = models.ForeignKey(Shop, models.DO_NOTHING)
    product = models.ForeignKey(Product, models.DO_NOTHING, related_name="batches")
    quantity_received = models.DecimalField(max_digits=12, decimal_places=3)
    quantity_remaining = models.DecimalField(max_digits=12, decimal_places=3)
    expiry_date = models.DateField(null=True, blank=True)
    purchase_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    received_on = models.DateField()
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        managed = False
        db_table = "store_stockbatch"


class StockAdjustment(models.Model):
    shop = models.ForeignKey(Shop, models.DO_NOTHING)
    batch = models.ForeignKey(StockBatch, models.DO_NOTHING, related_name="adjustments")
    quantity_change = models.DecimalField(max_digits=12, decimal_places=3)
    reason = models.CharField(max_length=12)
    created_by = models.ForeignKey(ShopkeeperUser, models.DO_NOTHING)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "store_stockadjustment"


class Customer(models.Model):
    shop = models.ForeignKey(Shop, models.DO_NOTHING)
    name = models.CharField(max_length=120)
    whatsapp_number = models.CharField(max_length=10)
    address = models.TextField(blank=True)
    is_promotion_allowed = models.BooleanField(default=False)

    class Meta:
        managed = False
        db_table = "store_customer"
        ordering = ["name"]


class Invoice(models.Model):
    shop = models.ForeignKey(Shop, models.DO_NOTHING)
    number = models.CharField(max_length=40)
    share_token = models.CharField(max_length=48, unique=True)
    customer = models.ForeignKey(Customer, models.DO_NOTHING, null=True, blank=True, related_name="invoices")
    date = models.DateTimeField()
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_type = models.CharField(max_length=10, default="CASH")
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=12, default="ACTIVE")
    created_by = models.ForeignKey(ShopkeeperUser, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = "store_invoice"
        ordering = ["-date"]


class InvoiceItem(models.Model):
    shop = models.ForeignKey(Shop, models.DO_NOTHING)
    invoice = models.ForeignKey(Invoice, models.DO_NOTHING, related_name="items")
    product = models.ForeignKey(Product, models.DO_NOTHING)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    gst_percent = models.PositiveSmallIntegerField(default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        managed = False
        db_table = "store_invoiceitem"


class InvoiceItemBatch(models.Model):
    shop = models.ForeignKey(Shop, models.DO_NOTHING)
    invoice_item = models.ForeignKey(InvoiceItem, models.DO_NOTHING, related_name="batch_allocations")
    batch = models.ForeignKey(StockBatch, models.DO_NOTHING)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)

    class Meta:
        managed = False
        db_table = "store_invoiceitembatch"


class CreditEntry(models.Model):
    shop = models.ForeignKey(Shop, models.DO_NOTHING)
    customer = models.ForeignKey(Customer, models.DO_NOTHING, related_name="credit_entries")
    entry_type = models.CharField(max_length=10)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    invoice = models.ForeignKey(Invoice, models.DO_NOTHING, null=True, blank=True)
    date = models.DateField()
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        managed = False
        db_table = "store_creditentry"


class Announcement(models.Model):
    title = models.CharField(max_length=160)
    message = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField()
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    targeted_shops = models.ManyToManyField(Shop, through="AnnouncementTarget", blank=True)

    class Meta:
        managed = False
        db_table = "store_announcement"
        ordering = ["-created_at"]


class AnnouncementTarget(models.Model):
    announcement = models.ForeignKey(Announcement, models.DO_NOTHING)
    shop = models.ForeignKey(Shop, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = "store_announcementtarget"


class PromotionLog(models.Model):
    shop = models.ForeignKey(Shop, models.DO_NOTHING)
    customer = models.ForeignKey(Customer, models.DO_NOTHING, related_name="promotion_logs")
    message = models.TextField()
    sent_on = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "store_promotionlog"
