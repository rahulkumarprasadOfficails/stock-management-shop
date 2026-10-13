from django.conf import settings
from django.http import HttpResponseForbidden


class AllowedIPMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.ALLOWED_IPS and request.META.get("REMOTE_ADDR") not in settings.ALLOWED_IPS:
            return HttpResponseForbidden("This control panel is not available from your IP address.")
        return self.get_response(request)
