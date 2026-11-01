"""Initialize the isolated agentlens_eval database without touching application history."""

import os
import subprocess
import sys

import psycopg
from psycopg import sql
from sqlalchemy import func, select
from sqlalchemy.engine import make_url

from agentlens.config import ROOT, Settings
from agentlens.db import Run, create_session


def main():
    settings = Settings()
    url = make_url(settings.database_url.get_secret_value())
    if url.database != "agentlens_eval":
        raise ValueError("Explicitly configure AGENTLENS_DATABASE_URL for agentlens_eval first")
    with psycopg.connect(
        host=url.host,
        port=url.port,
        user=url.username,
        password=url.password,
        dbname="postgres",
        autocommit=True,
    ) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname=%s", (url.database,)
        ).fetchone()
        if exists is None:
            connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(url.database)))
    commands = [
        ["-m", "alembic", "upgrade", "heads"],
        ["-m", "agentlens.cli", "checkpoint-setup"],
        ["-m", "agentlens.cli", "seed"],
        ["-m", "agentlens.cli", "seed", "--dataset", "datasets/week6/telemetry.json"],
        ["scripts/init_identities.py"],
    ]
    env = {**os.environ, "AGENTLENS_DATABASE_URL": url.render_as_string(hide_password=False)}
    subprocess.run([sys.executable, *commands[0]], cwd=ROOT, env=env, check=True)
    with create_session(settings) as session:
        if session.scalar(select(func.count()).select_from(Run)):
            raise ValueError("Evaluation database already has runs; no seed or overwrite performed")
    for command in commands[1:]:
        subprocess.run([sys.executable, *command], cwd=ROOT, env=env, check=True)
    if not (settings.embedding_path / "artifacts.json").exists():
        subprocess.run(
            [sys.executable, "scripts/download_embedding.py"], cwd=ROOT, env=env, check=True
        )
    subprocess.run(
        [sys.executable, "-m", "agentlens.cli", "knowledge-import"], cwd=ROOT, env=env, check=True
    )
    print("Isolated database ready: seeded telemetry and handbooks, no historical experience")


if __name__ == "__main__":
    main()
