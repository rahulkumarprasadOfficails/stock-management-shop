from io import BytesIO
import re
from xml.sax.saxutils import escape

from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from .models import Invoice, Shop
from .templatetags.shopsetu_tags import amount_words


def _text(value):
    return escape(str(value or "")).replace("\n", "<br/>")


def build_invoice_pdf(invoice, items):
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=f"Invoice {invoice.number}",
        author=invoice.shop.name,
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="ShopTitle", parent=styles["Title"], fontSize=18, leading=22,
        textColor=colors.HexColor("#115e59"), alignment=TA_CENTER, spaceAfter=3,
    ))
    styles.add(ParagraphStyle(
        name="ShopInfo", parent=styles["Normal"], fontSize=9, leading=12,
        alignment=TA_CENTER, textColor=colors.HexColor("#475569"),
    ))
    styles.add(ParagraphStyle(
        name="InvoiceTitle", parent=styles["Heading2"], fontSize=13, leading=17,
        alignment=TA_CENTER, textColor=colors.HexColor("#0f172a"), spaceBefore=8,
    ))
    styles.add(ParagraphStyle(
        name="SmallCell", parent=styles["Normal"], fontSize=8, leading=10,
    ))
    styles.add(ParagraphStyle(
        name="RightCell", parent=styles["SmallCell"], alignment=TA_RIGHT,
    ))
    story = [
        Paragraph(_text(invoice.shop.name), styles["ShopTitle"]),
        Paragraph(_text(invoice.shop.address), styles["ShopInfo"]),
        Paragraph(
            "Phone: %s%s" % (
                _text(invoice.shop.phone),
                f" &nbsp; | &nbsp; GSTIN: {_text(invoice.shop.gstin)}" if invoice.shop.gstin else "",
            ),
            styles["ShopInfo"],
        ),
        Paragraph(
            "Bill of Supply" if invoice.shop.invoice_type == Shop.InvoiceType.BILL_OF_SUPPLY else "Tax Invoice",
            styles["InvoiceTitle"],
        ),
        Spacer(1, 7 * mm),
    ]
    customer_name = invoice.customer.name if invoice.customer else "Walk-in customer"
    metadata = [
        ["Invoice", invoice.number, "Date", timezone.localtime(invoice.date).strftime("%d %b %Y, %I:%M %p")],
        ["Customer", customer_name, "Payment", invoice.get_payment_type_display()],
    ]
    meta_table = Table(metadata, colWidths=[23 * mm, 69 * mm, 22 * mm, 63 * mm])
    meta_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#64748b")),
        ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#64748b")),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTNAME", (3, 0), (3, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 5 * mm))

    taxable = invoice.shop.invoice_type == Shop.InvoiceType.TAX_INVOICE
    header = ["Item", "HSN", "Qty", "Rate"]
    if taxable:
        header.extend(["GST", "CGST", "SGST"])
    header.append("Amount")
    rows = [header]
    for item in items:
        row = [
            Paragraph(_text(item.product.name), styles["SmallCell"]),
            _text(item.product.hsn_code) or "-",
            f"{item.quantity:,.3f}".rstrip("0").rstrip("."),
            f"INR {item.unit_price:,.2f}",
        ]
        if taxable:
            half_tax = item.tax_amount / 2
            row.extend([
                f"{item.gst_percent}%",
                f"INR {half_tax:,.2f}",
                f"INR {half_tax:,.2f}",
            ])
        row.append(f"INR {item.line_total:,.2f}")
        rows.append(row)
    if taxable:
        widths = [42 * mm, 16 * mm, 14 * mm, 23 * mm, 13 * mm, 18 * mm, 18 * mm, 29 * mm]
    else:
        widths = [65 * mm, 23 * mm, 20 * mm, 35 * mm, 35 * mm]
    item_table = Table(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
    item_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#115e59")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, 0), 7),
        ("FONTSIZE", (1, 1), (-1, -1), 7),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#dbe4ec")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(item_table)
    story.append(Spacer(1, 6 * mm))

    totals = [["Subtotal", f"INR {invoice.subtotal:,.2f}"]]
    if taxable:
        totals.append(["Total tax", f"INR {invoice.total_tax:,.2f}"])
    totals.extend([
        ["Total", f"INR {invoice.total:,.2f}"],
        ["Paid", f"INR {invoice.amount_paid:,.2f}"],
        ["Balance", f"INR {invoice.total - invoice.amount_paid:,.2f}"],
    ])
    totals_table = Table(totals, colWidths=[43 * mm, 36 * mm], hAlign="RIGHT")
    totals_table.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEABOVE", (0, -4), (-1, -4), 0.8, colors.HexColor("#94a3b8")),
        ("FONTNAME", (0, -4), (-1, -4), "Helvetica-Bold"),
        ("FONTSIZE", (0, -4), (-1, -4), 11),
        ("TEXTCOLOR", (0, -4), (-1, -4), colors.HexColor("#115e59")),
    ]))
    story.extend([
        totals_table,
        Spacer(1, 5 * mm),
        Paragraph(
            f"<b>Amount in words:</b> {_text(amount_words(invoice.total))}",
            styles["Normal"],
        ),
        Spacer(1, 12 * mm),
        Paragraph("Thank you for shopping with us!", styles["ShopInfo"]),
    ])
    if invoice.status == Invoice.Status.CANCELLED:
        story.insert(4, Paragraph(
            "<b>CANCELLED</b>",
            ParagraphStyle(
                "Cancelled", parent=styles["Normal"], alignment=TA_CENTER,
                textColor=colors.HexColor("#b91c1c"), fontSize=14, spaceAfter=8,
            ),
        ))
    document.build(story)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    safe_number = re.sub(r"[^A-Za-z0-9_-]+", "-", invoice.number).strip("-") or "invoice"
    response["Content-Disposition"] = f'attachment; filename="{safe_number}.pdf"'
    return response
