from django.db.models import Q
from django.utils import timezone

from .models import Announcement, UserProfile


def announcements(request):
    now = timezone.now()
    items = Announcement.objects.filter(is_active=True).filter(
        Q(starts_at__isnull=True) | Q(starts_at__lte=now),
        Q(ends_at__isnull=True) | Q(ends_at__gt=now),
    )
    shop_id = None
    if request.user.is_authenticated:
        try:
            shop_id = request.user.profile.shop_id
        except UserProfile.DoesNotExist:
            pass
    if shop_id:
        items = items.filter(Q(targeted_shops__isnull=True) | Q(targeted_shops__id=shop_id))
    else:
        items = items.filter(targeted_shops__isnull=True)
    return {"active_announcements": items.distinct()}
