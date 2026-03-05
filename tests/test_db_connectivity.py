"""One-shot DB connectivity test.

Fetches the connection string from SSM, connects with SSL, and runs two checks:
  1. SELECT version()
  2. pgvector extension present

Run: python tests/test_db_connectivity.py
"""
import sys

import boto3
import psycopg2

REGION = "eu-west-1"
SSM_DB_CONNECTION_PARAM = "/ghost/dev/db/connection_string"


def fetch_dsn() -> str:
    print(f"[1/3] Fetching SSM parameter: {SSM_DB_CONNECTION_PARAM}")
    client = boto3.client("ssm", region_name=REGION)
    resp = client.get_parameter(Name=SSM_DB_CONNECTION_PARAM, WithDecryption=True)
    dsn = resp["Parameter"]["Value"]
    # Mask password in log output
    masked = dsn.split("@")[1] if "@" in dsn else dsn
    print(f"      Host: {masked}")
    return dsn


def run_checks(dsn: str) -> None:
    print("[2/3] Connecting with SSL ...")
    conn = psycopg2.connect(dsn, sslmode="require")
    cur = conn.cursor()

    print("[3/3] Running checks ...")

    cur.execute("SELECT version();")
    pg_version = cur.fetchone()[0]
    print(f"\n  PostgreSQL version:\n    {pg_version}")

    cur.execute("SELECT extname FROM pg_extension WHERE extname = 'vector';")
    row = cur.fetchone()
    if row:
        print(f"\n  pgvector extension: INSTALLED ({row[0]})")
    else:
        print("\n  pgvector extension: NOT FOUND — run 'CREATE EXTENSION vector;'")

    cur.close()
    conn.close()


def main() -> None:
    try:
        dsn = fetch_dsn()
        run_checks(dsn)
        print("\nAll checks passed.")
    except Exception as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
