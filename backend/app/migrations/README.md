# SmartPim Migrations

Alembic owns new schema changes from this point forward.

Current production already has the legacy runtime-created schema, so the first revision is a no-op baseline. Revision `20260607_0002` documents the operational workflow/channel tables that were previously created at runtime; revision `20260607_0003` documents the `json_documents` table used by the Postgres JSON store; revision `20260607_0004` documents auth/control-plane tables (`users`, `roles`, organizations, members, invites); revision `20260607_0005` documents connector settings and connected store tables; revision `20260607_0006` documents marketplace attribute provider bindings; revision `20260607_0007` documents catalog nodes and marketplace category mappings; revision `20260607_0008` documents legacy info-model attribute mapping rows; revision `20260607_0009` documents category attribute value reference rows; revision `20260607_0010` documents dictionary/value/export-map tables; revision `20260607_0011` documents info-model template tables and category-template resolution; revision `20260607_0012` documents core product, registry, product page and marketplace status tables. Do not add new runtime `CREATE TABLE` / `ALTER TABLE` blocks for new features; add an Alembic revision instead.

Run manually from `backend/`:

```bash
python scripts/run_migrations.py
```

Production deploy runs migrations only when `APP_RUN_DB_MIGRATIONS=1` is set.
