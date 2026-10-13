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
