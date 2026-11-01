"""Create the development database in the project-local PostgreSQL cluster."""

import psycopg

with psycopg.connect(
    "host=127.0.0.1 port=5432 dbname=postgres user=agentlens password=agentlens-local",
    autocommit=True,
) as connection:
    if (
        connection.execute("SELECT 1 FROM pg_database WHERE datname = 'agentlens'").fetchone()
        is None
    ):
        connection.execute("CREATE DATABASE agentlens")
print("Development database ready")
