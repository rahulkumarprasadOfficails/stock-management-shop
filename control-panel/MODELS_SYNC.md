# Mirror model sync

The `panel.models` business-data classes use `managed = False`; they do not create, alter, or drop ShopKeeper-owned tables. They point to the exact ShopKeeper table names in `public`, resolved through the `shopkeeper_control,public` PostgreSQL search path.

When ShopKeeper models or migrations change, update the corresponding mirror fields, relationships, and `db_table` values in `panel/models.py`. Keep these definitions aligned with `store/models.py` in ShopKeeper. The Control Panel must never run ShopKeeper migrations.

Announcements support optional `starts_at`, `ends_at`, and shop targeting. These fields and the `store_announcementtarget` join table are owned and migrated by the ShopKeeper app; run the ShopKeeper migration against the connected PostgreSQL database before using those Control Panel features.

Panel-owned PostgreSQL tables use the `shopkeeper_control` schema. The platform user table is named `control_adminuser`; it never writes the ShopKeeper `auth_user` table for panel authentication. The panel mirror `ShopkeeperUser` intentionally writes the existing `public.auth_user` table only for shopkeeper account management.
