import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import CreditEntry, Customer, Invoice, InvoiceItem, InvoiceItemBatch, Product, Shop, StockBatch

CENT = Decimal("0.01")
THOUSANDTH = Decimal("0.001")


def money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def calculate_credit_balance(customer):
    entries = customer.credit_entries.filter(shop_id=customer.shop_id)
    given = sum((row.amount for row in entries if row.entry_type == CreditEntry.EntryType.GIVEN), Decimal("0"))
    received = sum((row.amount for row in entries if row.entry_type == CreditEntry.EntryType.RECEIVED), Decimal("0"))
    return given - received


def _parse_lines(items_json):
    try:
        raw_lines = json.loads(items_json)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValidationError(_("Bill items are invalid.")) from exc
    if not isinstance(raw_lines, list) or not raw_lines:
        raise ValidationError(_("Add at least one product to the bill."))
    quantities = {}
    for row in raw_lines:
        if not isinstance(row, dict):
            raise ValidationError(_("Bill items are invalid."))
        try:
            product_id = int(row.get("product_id"))
            quantity = Decimal(str(row.get("quantity"))).quantize(THOUSANDTH)
        except (TypeError, ValueError, InvalidOperation) as exc:
            raise ValidationError(_("Enter a valid product and quantity.")) from exc
        if quantity <= 0:
            raise ValidationError(_("Quantity must be greater than zero."))
        quantities[product_id] = quantities.get(product_id, Decimal("0")) + quantity
    return quantities


@transaction.atomic
def create_invoice(*, user, shop, customer, payment_type, amount_paid, items_json):
    if customer and customer.shop_id != shop.id:
        raise ValidationError(_("Select a customer from your shop."))
    quantities = _parse_lines(items_json)
    products = {
        product.pk: product
        for product in Product.objects.for_user(user).select_for_update().filter(shop=shop, is_active=True, pk__in=quantities).order_by("pk")
    }
    if len(products) != len(quantities):
        raise ValidationError(_("One or more selected products are unavailable."))
    if payment_type == Invoice.PaymentType.CREDIT and not customer:
        raise ValidationError(_("Choose a customer for a credit sale."))

    today = timezone.localdate()
    allocations = {}
    totals = {}
    for product_id, quantity in quantities.items():
        product = products[product_id]
        batches = list(
            StockBatch.objects.for_user(user).select_for_update()
            .filter(shop=shop, product=product, quantity_remaining__gt=0)
            .filter(Q(expiry_date__isnull=True) | Q(expiry_date__gte=today))
            .order_by(F("expiry_date").asc(nulls_last=True), "received_on", "id")
        )
        left = quantity
        picked = []
        for batch in batches:
            take = min(left, batch.quantity_remaining)
            if take:
                picked.append((batch, take))
                left -= take
            if left == 0:
                break
        if left > 0:
            raise ValidationError(_("Not enough unexpired stock for %(product)s.") % {"product": product.name})
        allocations[product_id] = picked
        base = money(product.selling_price * quantity)
        tax_rate = Decimal(product.gst_percent) / Decimal("100")
        tax = money(base * tax_rate) if shop.invoice_type == Shop.InvoiceType.TAX_INVOICE else Decimal("0.00")
        totals[product_id] = (base, tax, money(base + tax))

    locked_shop = Shop.objects.select_for_update().get(pk=shop.pk)
    locked_shop.last_invoice_number += 1
    locked_shop.save(update_fields=["last_invoice_number"])
    number = f"{locked_shop.invoice_prefix}-{locked_shop.last_invoice_number:04d}"
    subtotal = sum((part[0] for part in totals.values()), Decimal("0.00"))
    tax_total = sum((part[1] for part in totals.values()), Decimal("0.00"))
    total = subtotal + tax_total
    paid = money(amount_paid or 0)
    if paid < 0 or paid > total:
        raise ValidationError(_("Amount paid must be between zero and the bill total."))
    if payment_type in (Invoice.PaymentType.CASH, Invoice.PaymentType.UPI) and paid != total:
        paid = total
    if payment_type == Invoice.PaymentType.CREDIT and paid < total and not customer:
        raise ValidationError(_("Choose a customer for the outstanding credit."))

    invoice = Invoice.objects.create(
        shop=shop, number=number, customer=customer, subtotal=subtotal, total_tax=tax_total,
        total=total, payment_type=payment_type, amount_paid=paid, created_by=user,
    )
    for product_id, quantity in quantities.items():
        product = products[product_id]
        base, tax, line_total = totals[product_id]
        item = InvoiceItem.objects.create(
            shop=shop, invoice=invoice, product=product, quantity=quantity,
            unit_price=product.selling_price, gst_percent=product.gst_percent,
            tax_amount=tax, line_total=line_total,
        )
        for batch, amount in allocations[product_id]:
            batch.quantity_remaining = F("quantity_remaining") - amount
            batch.save(update_fields=["quantity_remaining"])
            InvoiceItemBatch.objects.create(shop=shop, invoice_item=item, batch=batch, quantity=amount)
    due = total - paid
    if due > 0 and customer:
        CreditEntry.objects.create(
            shop=shop, customer=customer, entry_type=CreditEntry.EntryType.GIVEN,
            amount=due, invoice=invoice, note=f"Invoice {invoice.number}",
        )
    return invoice


@transaction.atomic
def cancel_invoice(*, invoice, user, shop):
    invoice = Invoice.objects.for_user(user).select_for_update().get(pk=invoice.pk, shop=shop)
    if invoice.status == Invoice.Status.CANCELLED:
        raise ValidationError(_("This invoice is already cancelled."))
    for allocation in InvoiceItemBatch.objects.for_user(user).select_for_update().filter(shop=shop, invoice_item__invoice=invoice):
        batch = StockBatch.objects.for_user(user).select_for_update().get(pk=allocation.batch_id, shop=shop)
        batch.quantity_remaining = F("quantity_remaining") + allocation.quantity
        batch.save(update_fields=["quantity_remaining"])
    for entry in CreditEntry.objects.for_user(user).filter(shop=shop, invoice=invoice, entry_type=CreditEntry.EntryType.GIVEN):
        customer = Customer.objects.select_for_update().get(
            pk=entry.customer_id, shop=shop,
        )
        outstanding = calculate_credit_balance(customer)
        reversal = min(entry.amount, max(outstanding, Decimal("0")))
        if reversal:
            CreditEntry.objects.create(
                shop=shop, customer=customer, entry_type=CreditEntry.EntryType.RECEIVED,
                amount=reversal, invoice=invoice, note=f"Reversal: cancelled {invoice.number}",
            )
    invoice.status = Invoice.Status.CANCELLED
    invoice.save(update_fields=["status"])
    return invoice
