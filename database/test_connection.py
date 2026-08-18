import os

import psycopg
from dotenv import load_dotenv

load_dotenv()

conn = psycopg.connect(
    host=os.getenv("POSTGRES_HOST"),
    port=os.getenv("POSTGRES_PORT"),
    dbname=os.getenv("POSTGRES_DB"),
    user=os.getenv("POSTGRES_USER"),
    password=os.getenv("POSTGRES_PASSWORD"),
    sslmode=os.getenv("POSTGRES_SSLMODE"),
)

with conn.cursor() as cur:
    cur.execute("SELECT current_database(), version();")
    database, version = cur.fetchone()


    print(f"Connected to: {database}")
    print(version)

conn.close()