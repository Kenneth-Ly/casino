"""Supabase/Postgres wrapper for the single global high-balance record."""
import os

import psycopg2
from psycopg2 import sql

TABLE = "global_record"


def get_connection():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def get_global_record(table=TABLE):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("SELECT balance FROM {}").format(sql.Identifier(table)))
            row = cur.fetchone()
            return row[0] if row else 50
    finally:
        conn.close()


def update_global_record(balance, table=TABLE):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("UPDATE {} SET balance = %s WHERE balance < %s").format(
                    sql.Identifier(table)
                ),
                (balance, balance),
            )
        conn.commit()
    finally:
        conn.close()
