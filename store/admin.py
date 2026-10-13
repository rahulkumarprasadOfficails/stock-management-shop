from django.contrib import admin

from .models import (
    Announcement, CreditEntry, Customer, Invoice, InvoiceItem, InvoiceItemBatch,
    Product, PromotionLog, Shop, StockAdjustment, StockBatch, UserProfile,
)


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "is_active", "valid_until", "created_at")
    list_filter = ("is_active", "invoice_type")
    search_fields = ("name", "owner_name", "phone")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "shop", "role", "must_change_password")
    list_filter = ("role", "shop")
    search_fields = ("user__username", "shop__name")


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("title", "message")
    readonly_fields = ("created_at",)


for model in (Product, StockBatch, StockAdjustment, Customer, Invoice, InvoiceItem, InvoiceItemBatch, CreditEntry, PromotionLog):
    admin.site.register(model)
