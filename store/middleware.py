from datetime import date

from django.shortcuts import redirect
from django.urls import reverse

from .models import UserProfile


class ShopAccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated and user.is_superuser:
            if not request.path.startswith("/platform-admin/"):
                return redirect("admin:index")
        if user.is_authenticated and not user.is_superuser:
            path = request.path
            allowed = {
                reverse("login"), reverse("logout"), reverse("password_change"),
                reverse("account_inactive"), reverse("manifest"), reverse("service_worker"), "/health/",
            }
            if path not in allowed and not path.startswith("/static/"):
                try:
                    profile = user.profile
                except UserProfile.DoesNotExist:
                    return redirect("account_inactive")
                shop = profile.shop
                if not shop.is_active or (shop.valid_until and shop.valid_until < date.today()):
                    return redirect("account_inactive")
                if profile.must_change_password:
                    return redirect("password_change")
                if not shop.setup_completed and profile.role == UserProfile.Role.OWNER and path != reverse("setup"):
                    return redirect("setup")
        return self.get_response(request)
