from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

import psycopg
from psycopg import sql
from dotenv import load_dotenv


# Load parent tables before child tables so foreign-key constraints succeed.
TABLE_ORDER = [
    "stores",
    "employee_roles",
    "employees",
    "employee_compensation_history",
    "employee_shifts",
    "customers",
    "brands",
    "categories",
    "products",
    "product_prices",
    "orders",
    "order_items",
    "payments",
    "return_reasons",
    "returns",
    "return_items",
    "protection_plans",
    "order_protection_plans",
    "warehouses",
    "suppliers",
    "purchase_orders",
    "purchase_order_items",
    "inventory_transactions",
    "inventory_snapshots",
    "promotions",
    "order_item_promotions",
    "date_dimension",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bulk-load the appliance retail CSV dataset into PostgreSQL."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/raw"),
        help="Directory containing the generated CSV files (default: data/raw)",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Path to the .env file (default: .env)",
    )
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="TRUNCATE all target tables before loading. Useful for a clean reload.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate files and show what would be loaded without touching PostgreSQL.",
    )
    return parser.parse_args()


def load_environment(env_file: Path) -> None:
    if not env_file.exists():
        raise FileNotFoundError(f"Environment file not found: {env_file}")

    load_dotenv(env_file)

    required = [
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_SSLMODE",
    ]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError(
            "Missing required environment variables: " + ", ".join(missing)
        )


def connection_string() -> str:
    return (
        f"host={os.environ['POSTGRES_HOST']} "
        f"port={os.environ['POSTGRES_PORT']} "
        f"dbname={os.environ['POSTGRES_DB']} "
        f"user={os.environ['POSTGRES_USER']} "
        f"password={os.environ['POSTGRES_PASSWORD']} "
        f"sslmode={os.environ['POSTGRES_SSLMODE']}"
    )


def csv_path_for(data_dir: Path, table: str) -> Path:
    return data_dir / f"{table}.csv"


def read_header(csv_path: Path) -> list[str]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        try:
            columns = next(reader)
        except StopIteration as exc:
            raise ValueError(f"CSV file is empty: {csv_path}") from exc

    columns = [column.strip() for column in columns]

    if not columns or any(not column for column in columns):
        raise ValueError(f"Invalid or blank CSV header in: {csv_path}")

    if len(columns) != len(set(columns)):
        raise ValueError(f"Duplicate column names in CSV header: {csv_path}")

    return columns


def validate_files(data_dir: Path) -> dict[str, tuple[Path, list[str]]]:
    if not data_dir.exists():
        raise FileNotFoundError(f"Data directory not found: {data_dir}")

    files: dict[str, tuple[Path, list[str]]] = {}
    missing: list[Path] = []

    for table in TABLE_ORDER:
        csv_path = csv_path_for(data_dir, table)
        if not csv_path.exists():
            missing.append(csv_path)
            continue
        files[table] = (csv_path, read_header(csv_path))

    if missing:
        missing_text = "\n".join(f"  - {path}" for path in missing)
        raise FileNotFoundError(
            f"Missing {len(missing)} expected CSV file(s):\n{missing_text}"
        )

    return files


def truncate_tables(cur: psycopg.Cursor) -> None:
    # CASCADE makes this robust to FK relationships. RESTART IDENTITY resets any
    # sequences in case the schema contains generated/serial identity columns.
    table_list = sql.SQL(", ").join(sql.Identifier(table) for table in TABLE_ORDER)
    statement = sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY CASCADE").format(table_list)
    cur.execute(statement)


def load_csv(cur: psycopg.Cursor, table: str, csv_path: Path, columns: list[str]) -> int:
    column_list = sql.SQL(", ").join(sql.Identifier(column) for column in columns)
    copy_statement = sql.SQL(
        "COPY {} ({}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE)"
    ).format(sql.Identifier(table), column_list)

    print(f"Loading {table:<30} <- {csv_path.name}")

    # Stream the CSV instead of reading the whole file into memory.
    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        with cur.copy(copy_statement) as copy:
            while chunk := file.read(1024 * 1024):
                copy.write(chunk)

    cur.execute(
        sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table))
    )
    return cur.fetchone()[0]


def verify_target_tables(cur: psycopg.Cursor) -> None:
    cur.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = ANY(%s)
        """,
        (TABLE_ORDER,),
    )
    existing = {row[0] for row in cur.fetchall()}
    missing = [table for table in TABLE_ORDER if table not in existing]

    if missing:
        raise RuntimeError(
            "These expected PostgreSQL tables do not exist: " + ", ".join(missing)
        )


def main() -> None:
    args = parse_args()
    load_environment(args.env_file)
    files = validate_files(args.data_dir)

    print(f"Validated {len(files)} CSV files in {args.data_dir.resolve()}")

    if args.dry_run:
        print("\nDry run only. Load order:")
        for number, table in enumerate(TABLE_ORDER, start=1):
            csv_path, columns = files[table]
            print(
                f"{number:>2}. {table:<30} "
                f"{csv_path.name} ({len(columns)} columns)"
            )
        return

    print(f"Connecting to {os.environ['POSTGRES_DB']} on {os.environ['POSTGRES_HOST']}...")

    # One transaction for the full load. If any COPY fails, PostgreSQL rolls
    # everything back so the database isn't left partially populated.
    with psycopg.connect(connection_string()) as conn:
        with conn.cursor() as cur:
            verify_target_tables(cur)

            if args.truncate:
                print("Truncating target tables...")
                truncate_tables(cur)

            print("\nStarting bulk load...\n")
            counts: dict[str, int] = {}

            for table in TABLE_ORDER:
                csv_path, columns = files[table]
                counts[table] = load_csv(cur, table, csv_path, columns)
                print(f"  -> {counts[table]:,} rows in {table}\n")

        # Context manager commits automatically here if no exception occurred.

    print("Load completed successfully.\n")
    print("Final row counts:")
    for table in TABLE_ORDER:
        print(f"  {table:<30} {counts[table]:>12,}")


if __name__ == "__main__":
    main()
