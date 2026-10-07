"""
Writes the synthetic cases (seeded bugs and clean changes) in cases/ as unified diffs,
from the before/after sources below. Run from the repository root:

    python evals/review/build_synthetic_cases.py

The real cases (real-*.diff) come from CodeMop's own git history; see cases.yml.
"""
import difflib
from pathlib import Path

CASES = Path(__file__).parent / "cases"


def diff(path: str, before: str, after: str) -> str:
    old = before.splitlines(keepends=True) if before else []
    new = after.splitlines(keepends=True)
    header = f"diff --git a/{path} b/{path}\n"
    if not before:
        header += "new file mode 100644\n"
    lines = difflib.unified_diff(
        old, new, fromfile=f"a/{path}" if before else "/dev/null", tofile=f"b/{path}", n=3
    )
    return header + "".join(lines)


SYNTHETIC = {
    # ---- seeded bugs: one clear bug each ----
    "seeded-pagination": diff("api/listing.py", '''\
def list_orders(orders, page_size=20):
    """Return the first page of orders"""
    return orders[:page_size]
''', '''\
def list_orders(orders, page=1, page_size=20):
    """Return one page of orders; pages are numbered from 1"""
    start = page * page_size
    return orders[start:start + page_size]
'''),
    "seeded-sql-injection": diff("store/users.py", '''\
def find_user(conn, email):
    cur = conn.cursor()
    cur.execute("SELECT id, email FROM users WHERE email = %s", (email,))
    return cur.fetchone()
''', '''\
def find_user(conn, email):
    cur = conn.cursor()
    cur.execute("SELECT id, email FROM users WHERE email = %s", (email,))
    return cur.fetchone()


def search_users(conn, name_fragment, limit=50):
    """Users whose name contains `name_fragment`"""
    cur = conn.cursor()
    cur.execute(
        f"SELECT id, name FROM users WHERE name ILIKE '%{name_fragment}%' LIMIT {int(limit)}"
    )
    return cur.fetchall()
'''),
    "seeded-missing-await": diff("services/profile.py", '''\
async def get_profile(user_id, db, cache):
    cached = await cache.get(f"profile:{user_id}")
    if cached:
        return cached
    return await db.fetch_profile(user_id)
''', '''\
async def get_profile(user_id, db, cache):
    cached = await cache.get(f"profile:{user_id}")
    if cached:
        return cached
    profile = await db.fetch_profile(user_id)
    cache.set(f"profile:{user_id}", profile, ttl=300)
    return profile
'''),
    "seeded-mutable-default": diff("notify/email.py", '''\
def build_message(subject, body):
    return {"subject": subject, "body": body}
''', '''\
def build_message(subject, body, recipients=[]):
    """A message for `recipients`, always copying in the on-call address"""
    recipients.append("oncall@example.com")
    return {"subject": subject, "body": body, "to": recipients}
'''),
    "seeded-async-foreach": diff("src/sync.ts", '''\
export async function syncAll(accounts: Account[]): Promise<number> {
  return 0;
}
''', '''\
export async function syncAll(accounts: Account[]): Promise<number> {
  let synced = 0;
  accounts.forEach(async (account) => {
    await syncAccount(account);
    synced += 1;
  });
  return synced;
}
'''),
    "seeded-go-defer-before-err": diff("client/fetch.go", '''\
package client

import "net/http"

func Status(url string) (int, error) {
	return 0, nil
}
''', '''\
package client

import "net/http"

func Status(url string) (int, error) {
	resp, err := http.Get(url)
	defer resp.Body.Close()
	if err != nil {
		return 0, err
	}
	return resp.StatusCode, nil
}
'''),
    "seeded-inverted-expiry": diff("auth/tokens.py", '''\
from datetime import datetime, timezone


class TokenExpired(Exception):
    pass


def check_token(token):
    """Raise TokenExpired if the token can no longer be used"""
    pass
''', '''\
from datetime import datetime, timezone


class TokenExpired(Exception):
    pass


def check_token(token):
    """Raise TokenExpired if the token can no longer be used"""
    now = datetime.now(timezone.utc)
    if token.expires_at > now:
        raise TokenExpired(f"token {token.id} expired at {token.expires_at}")
'''),
    "seeded-assignment-in-condition": diff("src/admin.ts", '''\
export function canDeleteProject(user: User, project: Project): boolean {
  return false;
}
''', '''\
export function canDeleteProject(user: User, project: Project): boolean {
  if (project.ownerId === user.id) {
    return true;
  }
  if (user.role = "admin") {
    return true;
  }
  return false;
}
'''),
    "seeded-regex-prefix-validation": diff("ops/backup.py", '''\
import subprocess


def backup(database):
    subprocess.run(["pg_dump", "--file", "/backups/latest.sql", database], check=True)
''', '''\
import re
import subprocess


def backup(database):
    """Back up one database to /backups/<database>.sql"""
    if not re.match(r"[a-z_]+", database):
        raise ValueError(f"invalid database name: {database!r}")
    subprocess.run(f"pg_dump --file /backups/{database}.sql {database}", shell=True, check=True)
'''),

    # ---- clean changes: nothing wrong ----
    "clean-rename-refactor": diff("billing/invoice.py", '''\
def calc(items):
    t = 0
    for i in items:
        t += i.price * i.qty
    return t
''', '''\
def invoice_total(items):
    """The sum of price * quantity over the invoice's line items"""
    return sum(item.price * item.qty for item in items)
'''),
    "clean-add-tests": diff("tests/test_slugify.py", "", '''\
import pytest

from textutil import slugify


@pytest.mark.parametrize("title, slug", [
    ("Hello World", "hello-world"),
    ("  Trim me  ", "trim-me"),
    ("Already-slugged", "already-slugged"),
    ("Symbols & stuff!", "symbols-stuff"),
])
def test_slugify(title, slug):
    assert slugify(title) == slug


def test_empty_title():
    assert slugify("") == ""
'''),
    "clean-docs": diff("docs/deploying.md", '''\
# Deploying

Run `make deploy`.
''', '''\
# Deploying

1. Make sure CI is green on `main`.
2. Run `make deploy ENV=staging` and check the staging site.
3. Run `make deploy ENV=production`.

If a deploy fails, `make rollback ENV=production` restores the previous release.
'''),
    "clean-small-feature": diff("geo/distance.py", '''\
import math

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance between two points, in kilometres"""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))
''', '''\
import math

EARTH_RADIUS_KM = 6371.0
KM_PER_MILE = 1.609344


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance between two points, in kilometres"""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def haversine_miles(lat1, lon1, lat2, lon2):
    """Great-circle distance between two points, in miles"""
    return haversine_km(lat1, lon1, lat2, lon2) / KM_PER_MILE
'''),
}


if __name__ == "__main__":
    for name, text in SYNTHETIC.items():
        (CASES / f"{name}.diff").write_text(text)
        print(f"wrote {name}.diff")
