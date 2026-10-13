from decimal import Decimal
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils.crypto import get_random_string
from django.utils import timezone

from store.models import Customer, Product, Shop, StockBatch, UserProfile


class Command(BaseCommand):
    help = "Create a demo ShopSetu shop, owner login, products, stock, and customer."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="demo-owner")
        parser.add_argument("--password")

    def handle(self, *args, **options):
        username = options["username"]
        User = get_user_model()
        if User.objects.filter(username=username).exists():
            raise CommandError(f"Username '{username}' already exists.")
        password = options["password"] or get_random_string(16)
        shop = Shop.objects.create(
            name="Demo Kirana Store", owner_name="Shop Owner",
            address="Market Road, India", phone="9876543210",
            invoice_prefix="DEMO", setup_completed=True,
        )
        user = User.objects.create_user(username=username, password=password, first_name="Demo Owner")
        UserProfile.objects.create(user=user, shop=shop, role=UserProfile.Role.OWNER, must_change_password=True)
        for name, unit, price, gst in (
            ("Rice", Product.Unit.KG, "65.00", 5),
            ("Cooking oil", Product.Unit.LITRE, "145.00", 5),
            ("Bath soap", Product.Unit.PCS, "38.00", 18),
        ):
            product = Product.objects.create(
                shop=shop, name=name, unit=unit, selling_price=Decimal(price),
                purchase_price=Decimal(price) - Decimal("5.00"), gst_percent=gst,
                low_stock_limit=Decimal("5"),
            )
            StockBatch.objects.create(
                shop=shop, product=product, quantity_received=Decimal("25"),
                quantity_remaining=Decimal("25"), purchase_price=product.purchase_price,
                expiry_date=timezone.localdate() + timedelta(days=120),
            )
        Customer.objects.create(
            shop=shop, name="Demo Customer", whatsapp_number="9876543211",
            is_promotion_allowed=True,
        )
        self.stdout.write(self.style.SUCCESS(
            f"Created demo shop. Login username: {username}; temporary password: {password}"
        ))
