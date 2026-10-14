from decimal import Decimal

from django.contrib.auth.hashers import check_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    Announcement, AnnouncementTarget, AuditLog, CreditEntry, Customer,
    Invoice, InvoiceItem, InvoiceItemBatch, Product, PromotionLog, Shop,
    ShopkeeperUser, StockAdjustment, StockBatch, UserProfile,
)


MIRROR_MODELS = [
    Shop, ShopkeeperUser, UserProfile, Product, StockBatch, StockAdjustment,
    Customer, Invoice, InvoiceItem, InvoiceItemBatch, CreditEntry,
    Announcement, AnnouncementTarget, PromotionLog,
]


class ControlPanelTests(TestCase):
    @classmethod
    def setUpClass(cls):
        with connection.schema_editor() as schema_editor:
            for model in MIRROR_MODELS:
                schema_editor.create_model(model)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        with connection.schema_editor() as schema_editor:
            for model in reversed(MIRROR_MODELS):
                schema_editor.delete_model(model)

    @classmethod
    def setUpTestData(cls):
        from .models import AdminUser

        cls.admin = AdminUser.objects.create_superuser(
            username="platform-owner", email="owner@example.com", password="Platform-Test-Password-84!",
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def create_shop(self):
        response = self.client.post(reverse("shop_create"), {
            "name": "Sample Shop", "owner_name": "Shop Owner", "phone": "9876543210",
            "address": "1 Main Street", "gstin": "", "invoice_prefix": "SMP",
            "invoice_type": "TAX_INVOICE", "username": "sample-owner",
        })
        self.assertEqual(response.status_code, 200)
        return Shop.objects.get(name="Sample Shop")

    def test_shop_creation_creates_shopkeeper_user_and_profile_and_audit(self):
        response = self.client.post(reverse("shop_create"), {
            "name": "First Shop", "owner_name": "First Owner", "phone": "9876543210",
            "address": "Main Street", "gstin": "", "invoice_prefix": "FS",
            "invoice_type": "TAX_INVOICE", "username": "first-owner",
        })
        self.assertEqual(response.status_code, 200)
        shop = Shop.objects.get(name="First Shop")
        user = ShopkeeperUser.objects.get(username="first-owner")
        profile = UserProfile.objects.get(user=user)
        self.assertEqual(profile.shop, shop)
        self.assertEqual(profile.role, "OWNER")
        self.assertTrue(profile.must_change_password)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(check_password(response.context["temporary_password"], user.password))
        validate_password(response.context["temporary_password"])
        self.assertTrue(AuditLog.objects.filter(action="shop.created", object_id=str(shop.pk)).exists())
        self.assertContains(response, "Send via WhatsApp")

    def test_deactivating_shop_sets_shopkeeper_access_flag_and_audits(self):
        shop = self.create_shop()
        response = self.client.post(reverse("shop_action", args=[shop.pk]), {"action": "deactivate"})
        self.assertEqual(response.status_code, 302)
        shop.refresh_from_db()
        self.assertFalse(shop.is_active)
        self.assertTrue(AuditLog.objects.filter(action="shop.deactivated", object_id=str(shop.pk)).exists())

    def test_permanent_shop_deletion_requires_exact_name_and_removes_shop_logins(self):
        shop = self.create_shop()
        profile = UserProfile.objects.select_related("user").get(shop=shop)
        user_id = profile.user_id
        product = Product.objects.create(
            shop=shop, name="Test item", unit="pcs", selling_price=Decimal("10.00"),
        )
        batch = StockBatch.objects.create(
            shop=shop, product=product, quantity_received=Decimal("5"),
            quantity_remaining=Decimal("5"), received_on=timezone.localdate(),
        )
        StockAdjustment.objects.create(
            shop=shop, batch=batch, quantity_change=Decimal("-1"), reason="DAMAGED",
            created_by_id=user_id, created_at=timezone.now(),
        )
        customer = Customer.objects.create(
            shop=shop, name="Test customer", whatsapp_number="9876543210",
        )
        invoice = Invoice.objects.create(
            shop=shop, number="SMP-1", share_token="test-shop-delete-token",
            customer=customer, date=timezone.now(), created_by_id=user_id,
        )
        invoice_item = InvoiceItem.objects.create(
            shop=shop, invoice=invoice, product=product, quantity=Decimal("1"),
            unit_price=Decimal("10.00"), tax_amount=Decimal("0.00"),
            line_total=Decimal("10.00"),
        )
        InvoiceItemBatch.objects.create(
            shop=shop, invoice_item=invoice_item, batch=batch, quantity=Decimal("1"),
        )
        CreditEntry.objects.create(
            shop=shop, customer=customer, invoice=invoice, entry_type="GIVEN",
            amount=Decimal("10.00"), date=timezone.localdate(),
        )
        PromotionLog.objects.create(
            shop=shop, customer=customer, message="Test message", sent_on=timezone.now(),
        )
        announcement = Announcement.objects.create(
            title="Test announcement", message="Test message", created_at=timezone.now(),
        )
        AnnouncementTarget.objects.create(announcement=announcement, shop=shop)

        response = self.client.post(reverse("shop_action", args=[shop.pk]), {
            "action": "delete", "confirm_shop_name": "wrong name",
        })
        self.assertRedirects(response, reverse("shop_detail", args=[shop.pk]))
        self.assertTrue(Shop.objects.filter(pk=shop.pk).exists())
        self.assertTrue(ShopkeeperUser.objects.filter(pk=user_id).exists())

        deactivate_response = self.client.post(reverse("shop_action", args=[shop.pk]), {
            "action": "deactivate",
        })
        self.assertRedirects(deactivate_response, reverse("shop_detail", args=[shop.pk]))
        shop.refresh_from_db()
        self.assertFalse(shop.is_active)

        delete_response = self.client.post(reverse("shop_action", args=[shop.pk]), {
            "action": "delete", "confirm_shop_name": shop.name,
        })
        self.assertRedirects(delete_response, reverse("shop_list"))
        self.assertFalse(Shop.objects.filter(pk=shop.pk).exists())
        self.assertFalse(UserProfile.objects.filter(shop_id=shop.pk).exists())
        self.assertFalse(ShopkeeperUser.objects.filter(pk=user_id).exists())
        for model in (
            Product, StockBatch, StockAdjustment, Customer, Invoice,
            InvoiceItem, InvoiceItemBatch, CreditEntry, PromotionLog,
            AnnouncementTarget,
        ):
            with self.subTest(model=model.__name__):
                self.assertFalse(model.objects.filter(shop_id=shop.pk).exists())
        self.assertTrue(AuditLog.objects.filter(
            action="shop.deleted", object_id=str(shop.pk),
            details__name="Sample Shop",
        ).exists())

    def test_password_reset_requires_change_and_audits_without_storing_password(self):
        shop = self.create_shop()
        profile = UserProfile.objects.select_related("user").get(shop=shop)
        response = self.client.post(reverse("user_password_reset", args=[shop.pk, profile.user_id]))
        self.assertEqual(response.status_code, 200)
        profile.refresh_from_db()
        profile.user.refresh_from_db()
        self.assertTrue(profile.must_change_password)
        self.assertTrue(check_password(response.context["temporary_password"], profile.user.password))
        audit = AuditLog.objects.get(action="user.password_reset")
        self.assertNotIn(response.context["temporary_password"], str(audit.details))

    def test_sensitive_actions_are_audited(self):
        shop = self.create_shop()
        self.client.post(reverse("shop_action", args=[shop.pk]), {"action": "activate"})
        self.assertTrue(AuditLog.objects.filter(actor=self.admin, object_type="Shop").exists())

    def test_non_staff_user_cannot_access_private_dashboard(self):
        from .models import AdminUser

        ordinary_user = AdminUser.objects.create_user("ordinary", password="Long-Password-998!")
        self.client.force_login(ordinary_user)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_sign_in_rejects_non_staff_account(self):
        from .models import AdminUser

        AdminUser.objects.create_user("ordinary-login", password="Long-Password-998!")
        self.client.logout()
        response = self.client.post(reverse("login"), {
            "username": "ordinary-login", "password": "Long-Password-998!",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_control_panel_password_policy_requires_complexity(self):
        with self.assertRaises(ValidationError):
            validate_password("only-lowercase-password")

    def test_main_management_pages_render_for_staff(self):
        shop = self.create_shop()
        for name, args in (
            ("dashboard", ()), ("shop_list", ()), ("shop_detail", (shop.pk,)),
            ("support", (shop.pk,)), ("announcements", ()), ("usage", ()),
            ("audit_log", ()),
        ):
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200)

    def test_announcement_create_writes_shared_announcement_and_audit(self):
        response = self.client.post(reverse("announcement_create"), {
            "title": "Maintenance", "message": "The service will be updated.",
            "is_active": "on", "starts_at": "", "ends_at": "",
        })
        self.assertEqual(response.status_code, 302)
        item = Announcement.objects.get(title="Maintenance")
        self.assertTrue(item.is_active)
        self.assertTrue(AuditLog.objects.filter(
            action="announcement.published", object_id=str(item.pk),
        ).exists())
