import secrets
import string

from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.utils import timezone

from .models import AuditLog, Shop, ShopkeeperUser, UserProfile


def temporary_password():
    alphabet = string.ascii_letters + string.digits + "!@#$%_-"
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(20))
        if (any(char.islower() for char in password) and any(char.isupper() for char in password)
                and any(char.isdigit() for char in password) and any(char in "!@#$%_-" for char in password)):
            return password


@transaction.atomic
def create_shop_with_owner(*, form_data, actor):
    password = temporary_password()
    shop = Shop.objects.create(
        name=form_data["name"], owner_name=form_data["owner_name"],
        phone=form_data["phone"], address=form_data["address"],
        gstin=form_data["gstin"], invoice_prefix=form_data["invoice_prefix"],
        invoice_type=form_data["invoice_type"], is_active=True,
        created_at=timezone.now(), setup_completed=True,
    )
    owner = ShopkeeperUser.objects.create(
        username=form_data["username"], password=make_password(password),
        first_name=form_data["owner_name"], is_staff=False, is_superuser=False,
        is_active=True, date_joined=timezone.now(),
    )
    UserProfile.objects.create(
        user=owner, shop=shop, role="OWNER", must_change_password=True,
    )
    AuditLog.objects.create(
        actor=actor, action="shop.created", object_type="Shop", object_id=str(shop.pk),
        details={"shop": shop.name, "owner_username": owner.username},
    )
    return shop, owner, password


def log_action(actor, action, *, object_type="", object_id="", details=None):
    return AuditLog.objects.create(
        actor=actor, action=action, object_type=object_type,
        object_id=str(object_id), details=details or {},
    )
