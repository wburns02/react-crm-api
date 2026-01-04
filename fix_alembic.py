#!/usr/bin/env python3
"""Fix alembic_version table to point to latest revision."""
import os
import psycopg2

url = os.environ.get('DATABASE_URL', '')
url = url.replace('postgresql+asyncpg://', 'postgresql://')
print(f"Connecting to database...")

conn = psycopg2.connect(url)
cur = conn.cursor()

# Check current
cur.execute('SELECT version_num FROM alembic_version')
rows = cur.fetchall()
print(f"Current version: {rows}")

# Stamp to latest (010_add_job_costs) since tables already exist
cur.execute('DELETE FROM alembic_version')
cur.execute("INSERT INTO alembic_version (version_num) VALUES ('010_add_job_costs')")
conn.commit()

# Verify
cur.execute('SELECT version_num FROM alembic_version')
rows = cur.fetchall()
print(f"New version: {rows}")

cur.close()
conn.close()
print("Done! Database is now at latest migration.")
