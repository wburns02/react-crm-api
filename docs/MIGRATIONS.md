# Database Migrations Guide

## Overview

This project uses Alembic for database migrations with PostgreSQL on Railway.

## Quick Reference

### Running Migrations Locally

```bash
# Apply all pending migrations
alembic upgrade head

# Check current version
alembic current

# View migration history
alembic history

# Downgrade one version
alembic downgrade -1

# Downgrade to specific version
alembic downgrade 013_fix_journey_schema
```

### Running Migrations on Railway

```bash
# Connect to Railway project
railway link

# Run migrations on production
railway run alembic upgrade head

# Check current production version
railway run alembic current

# View history on production
railway run alembic history
```

## Troubleshooting

### Version Mismatch

If the database has tables that don't match the alembic_version, stamp to sync:

```bash
# Check current version
railway run alembic current

# Stamp to a specific version (without running migration)
railway run alembic stamp 013_fix_journey_schema

# Then upgrade from there
railway run alembic upgrade head
```

### Column Name Issues

Always verify column names match the actual database schema before writing migrations:

```bash
# Check table schema on Railway
railway run python -c "
from sqlalchemy import create_engine, inspect
from app.core.config import settings
engine = create_engine(settings.DATABASE_URL.replace('+asyncpg', ''))
inspector = inspect(engine)
for col in inspector.get_columns('cs_journey_steps'):
    print(f\"{col['name']}: {col['type']}\")
"
```

### Common Column Name Mappings

| Migration 012 Schema | Common Mistake |
|---------------------|----------------|
| `config` | `action_config` |
| `wait_hours` | `wait_duration_hours` |
| `condition_rules` | ✓ (correct) |

## Creating New Migrations

### Auto-generate from models

```bash
alembic revision --autogenerate -m "description"
```

### Manual migration

```bash
alembic revision -m "description"
```

### Migration Template

```python
"""Description

Revision ID: XXX_description
Revises: previous_revision
Create Date: YYYY-MM-DD
"""
from alembic import op
import sqlalchemy as sa

revision = 'XXX_description'
down_revision = 'previous_revision'
branch_labels = None
depends_on = None

def upgrade():
    # Your upgrade SQL/operations
    op.execute("""
        INSERT INTO table_name (col1, col2) VALUES ('val1', 'val2');
    """)

def downgrade():
    # Reverse the upgrade
    op.execute("""
        DELETE FROM table_name WHERE col1 = 'val1';
    """)
```

## Deployment

Railway automatically runs migrations on deploy via the start command in `railway.json`:

```json
{
  "deploy": {
    "startCommand": "sh -c 'alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}'"
  }
}
```

## Migration Files Location

```
alembic/
├── versions/
│   ├── 001_add_technicians_and_invoices.py
│   ├── 002_add_payments_quotes_sms_consent.py
│   ├── ...
│   ├── 012_add_customer_success_platform.py
│   ├── 013_fix_journey_schema.py
│   └── 014_seed_journey_steps.py
├── env.py
└── script.py.mako
```

## Best Practices

1. **Always test locally first** before pushing migrations
2. **Use `op.execute()` for raw SQL** when seeding data
3. **Include downgrade()** for rollback capability
4. **Check column names** against actual schema before writing INSERTs
5. **Use conditional inserts** with `NOT EXISTS` to prevent duplicates
6. **Commit migrations separately** from feature code when possible
