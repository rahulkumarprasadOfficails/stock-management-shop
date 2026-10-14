import secrets
import string

from django.contrib.auth.hashers import make_password
from django.db import connection, transaction
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


@transaction.atomic
def delete_shop_permanently(*, shop_id, confirmed_name, actor):
    shop = Shop.objects.select_for_update().filter(pk=shop_id).first()
    if shop is None or shop.name != confirmed_name:
        return None

    user_ids = list(UserProfile.objects.filter(shop_id=shop_id).values_list("user_id", flat=True))
    usernames = list(ShopkeeperUser.objects.filter(pk__in=user_ids).values_list("username", flat=True))
    record_counts = {}
    with connection.cursor() as cursor:
        for table in (
            "store_announcementtarget",
            "store_invoiceitembatch",
            "store_invoiceitem",
            "store_creditentry",
            "store_stockadjustment",
            "store_promotionlog",
            "store_invoice",
            "store_stockbatch",
            "store_product",
            "store_customer",
            "store_userprofile",
        ):
            cursor.execute(f"DELETE FROM {table} WHERE shop_id = %s", [shop_id])
            record_counts[table] = cursor.rowcount

        if connection.vendor == "postgresql":
            cursor.execute("SELECT to_regclass(%s)", ["public.axes_accessattempt"])
            if cursor.fetchone()[0]:
                for username in usernames:
                    cursor.execute(
                        "DELETE FROM public.axes_accessattempt WHERE username = %s",
                        [username],
                    )

        for user_id in user_ids:
            cursor.execute("DELETE FROM auth_user WHERE id = %s", [user_id])
        record_counts["auth_user"] = len(user_ids)
        cursor.execute("DELETE FROM store_shop WHERE id = %s", [shop_id])
        record_counts["store_shop"] = cursor.rowcount

    log_action(
        actor, "shop.deleted", object_type="Shop", object_id=shop_id,
        details={"name": shop.name, "deleted_records": record_counts},
    )
    return record_counts
