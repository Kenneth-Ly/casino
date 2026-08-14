import os

import psycopg2
import pytest

from web import db

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set"
)

TEST_TABLE = "global_record_test"


@pytest.fixture(autouse=True)
def reset_test_table():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    with conn.cursor() as cur:
        cur.execute(f"UPDATE {TEST_TABLE} SET balance = 50")
    conn.commit()
    conn.close()
    yield


def test_get_global_record_returns_seeded_value():
    assert db.get_global_record(table=TEST_TABLE) == 50


def test_update_global_record_applies_when_higher():
    db.update_global_record(75, table=TEST_TABLE)
    assert db.get_global_record(table=TEST_TABLE) == 75


def test_update_global_record_ignores_lower_value():
    db.update_global_record(75, table=TEST_TABLE)
    db.update_global_record(60, table=TEST_TABLE)
    assert db.get_global_record(table=TEST_TABLE) == 75
