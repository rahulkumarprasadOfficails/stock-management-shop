from django.http import HttpResponseForbidden


def lockout_response(request, credentials, *args, **kwargs):
    return HttpResponseForbidden("Too many failed sign-in attempts. Try again later.")
