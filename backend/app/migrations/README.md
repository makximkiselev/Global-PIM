# SmartPim Migrations

Alembic owns new schema changes from this point forward.

Current production already has the legacy runtime-created schema, so the first revision is a no-op baseline. Revision `20260607_0002` documents the operational workflow/channel tables that were previously created at runtime; revision `20260607_0003` documents the `json_documents` table used by the Postgres JSON store; revision `20260607_0004` documents auth/control-plane tables (`users`, `roles`, organizations, members, invites). Do not add new runtime `CREATE TABLE` / `ALTER TABLE` blocks for new features; add an Alembic revision instead.

Run manually from `backend/`:

```bash
python scripts/run_migrations.py
```

Production deploy runs migrations only when `APP_RUN_DB_MIGRATIONS=1` is set.
