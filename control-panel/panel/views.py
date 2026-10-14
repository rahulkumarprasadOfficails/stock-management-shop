import csv
import calendar
from datetime import timedelta
from decimal import Decimal
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import make_password
from django.core.paginator import Paginator
from django.db import connection, transaction
from django.db.models import Count, Max, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.db.models.functions import Coalesce
from django.views.decorators.http import require_POST

from .forms import (
    AnnouncementForm, ControlLoginForm, ShopCreateForm, ShopEditForm,
    StockFixForm, ValidUntilForm,
)
from .models import (
    Announcement, AnnouncementTarget, AuditLog, Customer, Invoice, Product,
    Shop, ShopkeeperUser, StockBatch, UserProfile,
)
from .services import (
    create_shop_with_owner, delete_shop_permanently, log_action, temporary_password,
)


def staff_required(view_func):
    @login_required
    def wrapped(request, *args, **kwargs):
        if not (request.user.is_staff or request.user.is_superuser):
            return HttpResponse("Forbidden", status=403)
        return view_func(request, *args, **kwargs)
    return wrapped


def sign_in(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = ControlLoginForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        from django.contrib.auth import login
        login(request, form.get_user())
        return redirect("dashboard")
    return render(request, "panel/login.html", {"form": form})


@require_POST
@login_required
def sign_out(request):
    logout(request)
    return redirect("login")


@staff_required
def dashboard(request):
    today = timezone.localdate()
    month_start = today.replace(day=1)
    cutoff = timezone.now() - timedelta(days=7)
    shops = Shop.objects.all().annotate(last_login=Max("profiles__user__last_login"))
    context = {
        "shop_count": shops.count(),
        "active_count": shops.filter(is_active=True).count(),
        "expired_count": shops.filter(valid_until__lt=today).count(),
        "inactive_week_count": shops.filter(
            Q(last_login__lt=cutoff) |
            Q(last_login__isnull=True, created_at__date__lt=cutoff.date())
        ).count(),
        "invoice_count": Invoice.objects.filter(date__date__gte=month_start, date__date__lte=today).count(),
        "new_shop_count": shops.filter(created_at__date__gte=month_start, created_at__date__lte=today).count(),
        "recent_shops": shops.order_by("-created_at")[:8],
    }
    return render(request, "panel/dashboard.html", context)


@staff_required
def shop_list(request):
    today = timezone.localdate()
    shops = Shop.objects.all().annotate(
        last_login=Max("profiles__user__last_login"),
        bill_count=Count("invoice", distinct=True),
    ).order_by("-created_at", "pk")
    query = request.GET.get("q", "").strip()
    if query:
        shops = shops.filter(Q(name__icontains=query) | Q(phone__icontains=query) | Q(gstin__icontains=query))
    status = request.GET.get("status", "")
    if status == "active":
        shops = shops.filter(is_active=True)
    elif status == "inactive":
        shops = shops.filter(is_active=False)
    elif status == "expiring":
        shops = shops.filter(is_active=True, valid_until__range=(today, today + timedelta(days=7)))
    elif status == "expired":
        shops = shops.filter(valid_until__lt=today)
    sort = request.GET.get("sort", "-created_at")
    if sort in {"last_login", "-last_login", "bill_count", "-bill_count", "name", "-name"}:
        shops = shops.order_by(sort, "pk")
    paginator = Paginator(shops, 20)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "panel/shop_list.html", {
        "page_obj": page, "query": query, "status": status, "sort": sort,
    })


@staff_required
def shop_create(request):
    form = ShopCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        shop, owner, password = create_shop_with_owner(
            form_data=form.cleaned_data, actor=request.user,
        )
        text = (
            f"ShopKeeper login for {shop.name}\n"
            f"Username: {owner.username}\n"
            f"Temporary password: {password}\n"
            "Please change this password after your first login."
        )
        whatsapp_url = f"https://wa.me/91{shop.phone}?{urlencode({'text': text})}"
        return render(request, "panel/shop_created.html", {
            "shop": shop, "owner": owner, "temporary_password": password,
            "whatsapp_url": whatsapp_url,
        })
    return render(request, "panel/shop_form.html", {"form": form})


@staff_required
def shop_detail(request, pk):
    shop = get_object_or_404(Shop.objects.annotate(last_login=Max("profiles__user__last_login")), pk=pk)
    today = timezone.localdate()
    month_start = today.replace(day=1)
    invoices = Invoice.objects.filter(shop=shop)
    context = {
        "shop": shop,
        "users": UserProfile.objects.filter(shop=shop).select_related("user").order_by("user__username"),
        "product_count": Product.objects.filter(shop=shop).count(),
        "customer_count": Customer.objects.filter(shop=shop).count(),
        "invoice_count": invoices.count(),
        "month_invoice_count": invoices.filter(date__date__gte=month_start, date__date__lte=today).count(),
        "month_sales": invoices.filter(
            status="ACTIVE", date__date__gte=month_start, date__date__lte=today,
        ).aggregate(total=Sum("total"))["total"] or Decimal("0.00"),
        "valid_until_form": ValidUntilForm(initial={"valid_until": shop.valid_until}),
    }
    return render(request, "panel/shop_detail.html", context)


@staff_required
@require_POST
def shop_action(request, pk):
    shop = get_object_or_404(Shop, pk=pk)
    action = request.POST.get("action")
    if action in {"activate", "deactivate"}:
        with transaction.atomic():
            shop.is_active = action == "activate"
            shop.save(update_fields=["is_active"])
            log_action(request.user, f"shop.{action}d", object_type="Shop", object_id=shop.pk, details={"name": shop.name})
        messages.success(request, f"{shop.name} is now {'active' if shop.is_active else 'inactive'}.")
    elif action == "delete":
        confirmed_name = request.POST.get("confirm_shop_name", "").strip()
        if confirmed_name != shop.name:
            messages.error(request, "Type the exact shop name to confirm permanent deletion.")
            return redirect("shop_detail", pk=shop.pk)
        deleted_records = delete_shop_permanently(
            shop_id=shop.pk, confirmed_name=confirmed_name, actor=request.user,
        )
        if deleted_records is None:
            messages.error(request, "The shop changed or was already deleted. Refresh the shop list.")
            return redirect("shop_list")
        messages.success(
            request,
            f"{shop.name} and its business data and shop logins were permanently deleted.",
        )
        return redirect("shop_list")
    elif action == "extend":
        months = request.POST.get("months")
        if months not in {"1", "3", "12"}:
            messages.error(request, "Choose a valid renewal period.")
            return redirect("shop_detail", pk=shop.pk)
        base = max(shop.valid_until or timezone.localdate(), timezone.localdate())
        month_index = base.month - 1 + int(months)
        year = base.year + month_index // 12
        month = month_index % 12 + 1
        with transaction.atomic():
            shop.valid_until = base.replace(
                year=year, month=month, day=min(base.day, calendar.monthrange(year, month)[1]),
            )
            shop.save(update_fields=["valid_until"])
            log_action(request.user, "shop.validity_extended", object_type="Shop", object_id=shop.pk,
                       details={"valid_until": shop.valid_until.isoformat(), "months": int(months)})
        messages.success(request, f"Access extended through {shop.valid_until}.")
    elif action == "set_valid_until":
        form = ValidUntilForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Enter a valid expiry date.")
            return redirect("shop_detail", pk=shop.pk)
        with transaction.atomic():
            shop.valid_until = form.cleaned_data["valid_until"]
            shop.save(update_fields=["valid_until"])
            log_action(request.user, "shop.validity_set", object_type="Shop", object_id=shop.pk,
                       details={"valid_until": shop.valid_until.isoformat()})
        messages.success(request, "Shop validity updated.")
    else:
        messages.error(request, "Unknown shop action.")
    return redirect("shop_detail", pk=shop.pk)


@staff_required
def shop_edit(request, pk):
    shop = get_object_or_404(Shop, pk=pk)
    form = ShopEditForm(request.POST or None, instance=shop)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            form.save()
            log_action(request.user, "shop.updated", object_type="Shop", object_id=shop.pk)
        messages.success(request, "Shop details updated.")
        return redirect("shop_detail", pk=shop.pk)
    return render(request, "panel/shop_form.html", {"form": form, "shop": shop})


@staff_required
def user_password_reset(request, shop_pk, user_pk):
    profile = get_object_or_404(UserProfile.objects.select_related("user", "shop"), shop_id=shop_pk, user_id=user_pk)
    if request.method != "POST":
        return HttpResponse("Method not allowed", status=405)
    password = temporary_password()
    with transaction.atomic():
        profile.user.password = make_password(password)
        profile.user.save(update_fields=["password"])
        profile.must_change_password = True
        profile.save(update_fields=["must_change_password"])
        log_action(request.user, "user.password_reset", object_type="User", object_id=profile.user_id,
                   details={"username": profile.user.username, "shop_id": profile.shop_id})
    return render(request, "panel/password_reset.html", {"profile": profile, "temporary_password": password})


@staff_required
@require_POST
def user_unlock(request, shop_pk, user_pk):
    profile = get_object_or_404(UserProfile.objects.select_related("user"), shop_id=shop_pk, user_id=user_pk)
    table_exists = False
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass(%s)", ["public.axes_accessattempt"])
            table_exists = cursor.fetchone()[0] is not None
            if table_exists:
                cursor.execute("DELETE FROM public.axes_accessattempt WHERE username = %s", [profile.user.username])
                deleted = cursor.rowcount
            else:
                deleted = 0
        if table_exists:
            log_action(request.user, "user.unlocked", object_type="User", object_id=profile.user_id,
                       details={"username": profile.user.username, "attempts_removed": deleted})
    if not table_exists:
        messages.error(request, "The ShopKeeper django-axes table was not found in the public schema.")
        return redirect("shop_detail", pk=shop_pk)
    messages.success(request, f"Removed {deleted} lockout record(s) for {profile.user.username}.")
    return redirect("shop_detail", pk=shop_pk)


@staff_required
@require_POST
def user_deactivate(request, shop_pk, user_pk):
    profile = get_object_or_404(UserProfile.objects.select_related("user"), shop_id=shop_pk, user_id=user_pk)
    with transaction.atomic():
        profile.user.is_active = not profile.user.is_active
        profile.user.save(update_fields=["is_active"])
        action = "user.activated" if profile.user.is_active else "user.deactivated"
        log_action(request.user, action, object_type="User", object_id=profile.user_id,
                   details={"username": profile.user.username, "shop_id": shop_pk})
    messages.success(request, f"{profile.user.username} is now {'active' if profile.user.is_active else 'inactive'}.")
    return redirect("shop_detail", pk=shop_pk)


@staff_required
def support_view(request, pk):
    shop = get_object_or_404(Shop, pk=pk)
    products = Product.objects.filter(shop=shop).order_by("name")
    batches = StockBatch.objects.filter(shop=shop).select_related("product").order_by("expiry_date", "received_on")[:100]
    invoices = Invoice.objects.filter(shop=shop).select_related("customer").order_by("-date")[:25]
    credit_rows = Customer.objects.filter(shop=shop).annotate(
        credit_given=Coalesce(
            Sum("credit_entries__amount", filter=Q(credit_entries__entry_type="GIVEN")),
            Decimal("0.00"),
        ),
        payments=Coalesce(
            Sum("credit_entries__amount", filter=Q(credit_entries__entry_type="RECEIVED")),
            Decimal("0.00"),
        ),
    ).annotate(
        credit_balance=Coalesce(
            Sum("credit_entries__amount", filter=Q(credit_entries__entry_type="GIVEN")),
            Decimal("0.00"),
        ) - Coalesce(
            Sum("credit_entries__amount", filter=Q(credit_entries__entry_type="RECEIVED")),
            Decimal("0.00"),
        )
    ).order_by("name")
    return render(request, "panel/support.html", {
        "shop": shop, "products": products, "batches": batches,
        "invoices": invoices, "credit_rows": credit_rows,
    })


@staff_required
@require_POST
def stock_fix(request, shop_pk, batch_pk):
    form = StockFixForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Enter a non-negative quantity and a reason.")
        return redirect("support", pk=shop_pk)
    new_quantity = form.cleaned_data["quantity_remaining"]
    reason = form.cleaned_data["reason"].strip()
    if not reason:
        messages.error(request, "A reason is required.")
        return redirect("support", pk=shop_pk)
    with transaction.atomic():
        batch = get_object_or_404(
            StockBatch.objects.select_for_update().select_related("product"),
            shop_id=shop_pk, pk=batch_pk,
        )
        previous = batch.quantity_remaining
        StockBatch.objects.filter(pk=batch.pk, shop_id=shop_pk).update(quantity_remaining=new_quantity)
        log_action(request.user, "stock.quantity_fixed", object_type="StockBatch", object_id=batch.pk,
                   details={"shop_id": shop_pk, "product": batch.product.name,
                            "previous": str(previous), "new": str(new_quantity), "reason": reason})
    messages.success(request, "Stock quantity corrected and audit logged.")
    return redirect("support", pk=shop_pk)


@staff_required
def announcements(request):
    items = Announcement.objects.all().prefetch_related("targeted_shops").order_by("-created_at")
    return render(request, "panel/announcements.html", {"announcements": items})


@staff_required
def announcement_create(request):
    return announcement_form(request)


@staff_required
def announcement_edit(request, pk):
    announcement = get_object_or_404(Announcement, pk=pk)
    return announcement_form(request, announcement)


def announcement_form(request, announcement=None):
    form = AnnouncementForm(request.POST or None, instance=announcement)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            item = form.save(commit=False)
            if not item.pk:
                item.created_at = timezone.now()
            item.save()
            AnnouncementTarget.objects.filter(announcement=item).delete()
            AnnouncementTarget.objects.bulk_create([
                AnnouncementTarget(announcement=item, shop=shop)
                for shop in form.cleaned_data["targeted_shops"]
            ])
            log_action(request.user, "announcement.published" if item.is_active else "announcement.saved",
                       object_type="Announcement", object_id=item.pk,
                       details={"title": item.title, "active": item.is_active})
        messages.success(request, "Announcement saved.")
        return redirect("announcements")
    return render(request, "panel/announcement_form.html", {"form": form, "announcement": announcement})


@staff_required
@require_POST
def announcement_toggle(request, pk):
    item = get_object_or_404(Announcement, pk=pk)
    with transaction.atomic():
        item.is_active = not item.is_active
        item.save(update_fields=["is_active"])
        log_action(request.user, "announcement.enabled" if item.is_active else "announcement.disabled",
                   object_type="Announcement", object_id=item.pk, details={"title": item.title})
    return redirect("announcements")


def usage_queryset():
    now = timezone.now()
    return Shop.objects.annotate(
        last_login=Max("profiles__user__last_login"),
        recent_invoice_count=Count("invoice", filter=Q(invoice__date__gte=now - timedelta(days=30)), distinct=True),
        product_count=Count("product", distinct=True),
    ).order_by("name")


@staff_required
def usage_report(request):
    return render(request, "panel/usage.html", {"shops": usage_queryset()})


@staff_required
def usage_csv(request):
    response = csv_response("shopkeeper-usage.csv", ["shop", "last_login", "invoices_last_30_days", "products"])
    writer = csv.writer(response)
    for shop in usage_queryset():
        writer.writerow([shop.name, shop.last_login or "", shop.recent_invoice_count, shop.product_count])
    return response


@staff_required
def audit_log(request):
    logs = AuditLog.objects.select_related("actor")
    query = request.GET.get("q", "").strip()
    if query:
        logs = logs.filter(
            Q(actor__username__icontains=query) | Q(action__icontains=query) |
            Q(object_type__icontains=query) | Q(object_id__icontains=query)
        )
    start = parse_date(request.GET.get("from", ""))
    end = parse_date(request.GET.get("to", ""))
    if start:
        logs = logs.filter(created_at__date__gte=start)
    if end:
        logs = logs.filter(created_at__date__lte=end)
    page = Paginator(logs, 50).get_page(request.GET.get("page"))
    return render(request, "panel/audit_log.html", {"page_obj": page, "query": query})


@staff_required
def shop_export(request, pk):
    shop = get_object_or_404(Shop, pk=pk)
    data = {
        "shop": {"id": shop.pk, "name": shop.name},
        "products": list(Product.objects.filter(shop=shop).values(
            "id", "name", "unit", "selling_price", "purchase_price", "gst_percent",
            "hsn_code", "low_stock_limit", "is_active",
        )),
        "customers": list(Customer.objects.filter(shop=shop).values(
            "id", "name", "whatsapp_number", "address", "is_promotion_allowed",
        )),
        "invoices": list(Invoice.objects.filter(shop=shop).values(
            "id", "number", "date", "subtotal", "total_tax", "total", "payment_type",
            "amount_paid", "status", "customer_id",
        )),
    }
    if request.GET.get("format") == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="shop-{shop.pk}-export.csv"'
        writer = csv.writer(response)
        for section, rows in data.items():
            writer.writerow([section])
            if isinstance(rows, list) and rows:
                writer.writerow(rows[0].keys())
                for row in rows:
                    writer.writerow(row.values())
            elif isinstance(rows, dict):
                writer.writerow(rows.keys())
                writer.writerow(rows.values())
            writer.writerow([])
        return response
    response = JsonResponse(data, json_dumps_params={"default": str, "indent": 2})
    response["Content-Disposition"] = f'attachment; filename="shop-{shop.pk}-export.json"'
    return response


def csv_response(filename, headers):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    csv.writer(response).writerow(headers)
    return response


def health(_request):
    return JsonResponse({"status": "ok"})
