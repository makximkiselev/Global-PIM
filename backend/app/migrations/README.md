# SmartPim Migrations

Alembic owns new schema changes from this point forward.

Current production already has the legacy runtime-created schema, so the first revision is a no-op baseline. Do not add new runtime `CREATE TABLE` / `ALTER TABLE` blocks for new features; add an Alembic revision instead.

Run manually from `backend/`:

```bash
python scripts/run_migrations.py
```

Production deploy runs migrations only when `APP_RUN_DB_MIGRATIONS=1` is set.
