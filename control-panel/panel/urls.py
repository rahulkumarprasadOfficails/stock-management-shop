from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("login/", views.sign_in, name="login"),
    path("logout/", views.sign_out, name="logout"),
    path("", views.dashboard, name="dashboard"),
    path("shops/", views.shop_list, name="shop_list"),
    path("shops/create/", views.shop_create, name="shop_create"),
    path("shops/<int:pk>/", views.shop_detail, name="shop_detail"),
    path("shops/<int:pk>/edit/", views.shop_edit, name="shop_edit"),
    path("shops/<int:pk>/action/", views.shop_action, name="shop_action"),
    path("shops/<int:pk>/support/", views.support_view, name="support"),
    path("shops/<int:shop_pk>/users/<int:user_pk>/password/", views.user_password_reset, name="user_password_reset"),
    path("shops/<int:shop_pk>/users/<int:user_pk>/unlock/", views.user_unlock, name="user_unlock"),
    path("shops/<int:shop_pk>/users/<int:user_pk>/toggle/", views.user_deactivate, name="user_deactivate"),
    path("shops/<int:shop_pk>/batches/<int:batch_pk>/fix/", views.stock_fix, name="stock_fix"),
    path("shops/<int:pk>/export/", views.shop_export, name="shop_export"),
    path("announcements/", views.announcements, name="announcements"),
    path("announcements/create/", views.announcement_create, name="announcement_create"),
    path("announcements/<int:pk>/edit/", views.announcement_edit, name="announcement_edit"),
    path("announcements/<int:pk>/toggle/", views.announcement_toggle, name="announcement_toggle"),
    path("usage/", views.usage_report, name="usage"),
    path("usage.csv", views.usage_csv, name="usage_csv"),
    path("audit/", views.audit_log, name="audit_log"),
]
