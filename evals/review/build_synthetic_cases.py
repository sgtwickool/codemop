"""
Writes the synthetic cases (seeded bugs and clean changes) in cases/ as unified diffs,
from the before/after sources below; and for the cross-file cases, the repository after the
change in repos/<case>/, which is what repository context reads. Run from the repository root:

    python evals/review/build_synthetic_cases.py

The real cases (real-*.diff) come from CodeMop's own git history; see cases.yml.
"""
import difflib
import shutil
from pathlib import Path
from typing import Dict, NamedTuple

CASES = Path(__file__).parent / "cases"
REPOS = Path(__file__).parent / "repos"


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


class CrossFile(NamedTuple):
    """A change to one file, and the rest of the repository: where the change is used"""
    path: str
    before: str
    after: str
    others: Dict[str, str]


LEDGER_BEFORE = '''\
from payments.accounts import Account


class InsufficientFunds(Exception):
    pass


def transfer(amount, source: Account, target: Account):
    """Move `amount` (in cents) from one account to another"""
    if source.balance < amount:
        raise InsufficientFunds(source.id)
    source.balance -= amount
    target.balance += amount
'''

CROSS_FILE = {
    # ---- bugs that are only bugs because of how other files use the changed code ----
    "cross-file-arg-order": CrossFile("payments/ledger.py", LEDGER_BEFORE, LEDGER_BEFORE.replace(
        "def transfer(amount, source: Account, target: Account):\n"
        "    \"\"\"Move `amount` (in cents) from one account to another\"\"\"",
        "def transfer(source: Account, target: Account, amount: int):\n"
        "    \"\"\"Move `amount` (in cents) from one account to another (accounts first, like the rest of\n"
        "    the ledger)\"\"\""), {
        "payments/__init__.py": "",
        "payments/accounts.py": '''\
from dataclasses import dataclass


@dataclass
class Account:
    id: str
    balance: int = 0
''',
        "billing/__init__.py": "",
        "billing/invoices.py": '''\
from payments.ledger import InsufficientFunds, transfer


def pay_invoice(invoice, customer, shop):
    """Charge the customer for an invoice and mark it paid"""
    try:
        transfer(invoice.total, customer.account, shop.account)
    except InsufficientFunds:
        invoice.status = "declined"
        return False
    invoice.status = "paid"
    return True
''',
    }),
    "cross-file-none-instead-of-raise": CrossFile("accounts/users.py", '''\
from dataclasses import dataclass


class UserNotFound(Exception):
    pass


@dataclass
class User:
    id: int
    email: str
    password_hash: str

    def check_password(self, password, hasher):
        return hasher.verify(password, self.password_hash)


def find_user(db, email):
    """The user with this email address"""
    row = db.fetch_one("SELECT id, email, password_hash FROM users WHERE email = ?", (email,))
    if row is None:
        raise UserNotFound(email)
    return User(**row)
''', '''\
from dataclasses import dataclass
from typing import Optional


class UserNotFound(Exception):
    pass


@dataclass
class User:
    id: int
    email: str
    password_hash: str

    def check_password(self, password, hasher):
        return hasher.verify(password, self.password_hash)


def find_user(db, email) -> Optional["User"]:
    """The user with this email address, or None if there isn't one"""
    row = db.fetch_one("SELECT id, email, password_hash FROM users WHERE email = ?", (email.lower(),))
    if row is None:
        return None
    return User(**row)
''', {
        "accounts/__init__.py": "",
        "api/__init__.py": "",
        "api/login.py": '''\
from accounts.users import UserNotFound, find_user
from api.tokens import issue_token


def login(db, hasher, email, password):
    """POST /login: a session token for the right email and password"""
    try:
        user = find_user(db, email)
    except UserNotFound:
        return {"error": "Wrong email or password"}, 401
    if not user.check_password(password, hasher):
        return {"error": "Wrong email or password"}, 401
    return {"token": issue_token(user)}, 200
''',
        "api/tokens.py": '''\
import secrets


def issue_token(user):
    return f"{user.id}.{secrets.token_urlsafe(32)}"
''',
    }),
    "cross-file-units": CrossFile("config/settings.py", '''\
import os

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///app.db")
SESSION_TIMEOUT = 30  # minutes
REQUEST_TIMEOUT = 10
''', '''\
import os

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///app.db")
# Timeouts, all in seconds
SESSION_TIMEOUT = 30 * 60
REQUEST_TIMEOUT = 10
''', {
        "config/__init__.py": "",
        "auth/__init__.py": "",
        "auth/sessions.py": '''\
from datetime import datetime, timedelta, timezone

from config.settings import SESSION_TIMEOUT


def new_session(user_id, store):
    """Start a session that expires after SESSION_TIMEOUT"""
    expires = datetime.now(timezone.utc) + timedelta(minutes=SESSION_TIMEOUT)
    return store.create(user_id=user_id, expires=expires)


def is_active(session):
    return session.expires > datetime.now(timezone.utc)
''',
        "web/__init__.py": "",
        "web/client.py": '''\
import httpx

from config.settings import REQUEST_TIMEOUT


def fetch(url):
    return httpx.get(url, timeout=REQUEST_TIMEOUT)
''',
    }),
    "cross-file-sync-to-async": CrossFile("features/flags.py", '''\
import requests

FLAGS_URL = "https://flags.internal/api/flags"


def load_flags():
    """The feature flags for this deployment"""
    response = requests.get(FLAGS_URL, timeout=5)
    response.raise_for_status()
    return response.json()
''', '''\
import httpx

FLAGS_URL = "https://flags.internal/api/flags"


async def load_flags():
    """The feature flags for this deployment"""
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.get(FLAGS_URL)
    response.raise_for_status()
    return response.json()
''', {
        "features/__init__.py": "",
        "web/__init__.py": "",
        "web/views.py": '''\
from features.flags import load_flags


def home(request, render):
    """The home page, with the new dashboard for accounts in the beta"""
    flags = load_flags()
    template = "dashboard_v2.html" if flags.get("new_dashboard") else "dashboard.html"
    return render(template, user=request.user)
''',
    }),
    "cross-file-renamed-key": CrossFile("orders/serialize.py", '''\
def order_to_dict(order):
    """An order as JSON, for the API and the background jobs"""
    return {
        "id": order.id,
        "customer_id": order.customer_id,
        "total": order.total,
        "items": [{"sku": item.sku, "quantity": item.quantity} for item in order.items],
    }
''', '''\
def order_to_dict(order):
    """An order as JSON, for the API and the background jobs (camelCase, for the web app)"""
    return {
        "id": order.id,
        "customerId": order.customer_id,
        "total": order.total,
        "items": [{"sku": item.sku, "quantity": item.quantity} for item in order.items],
    }
''', {
        "orders/__init__.py": "",
        "jobs/__init__.py": "",
        "jobs/receipts.py": '''\
from orders.serialize import order_to_dict


def send_receipt(order, customers, mailer):
    """Email the customer a receipt for their order"""
    data = order_to_dict(order)
    customer = customers.get(data["customer_id"])
    mailer.send(customer.email, "Your receipt", f"Order {data['id']}: {data['total'] / 100:.2f}")
''',
    }),

    # ---- the same in TypeScript and JavaScript: bugs the compiler doesn't catch ----
    "cross-file-ts-units": CrossFile("src/lib/config.ts", '''\
export const APP_NAME = "Dayplan";
export const SESSION_TIMEOUT = 30; // minutes
export const UPLOAD_LIMIT_MB = 10;
''', '''\
export const APP_NAME = "Dayplan";
// Timeouts are in seconds, like every other duration in the app
export const SESSION_TIMEOUT = 30 * 60;
export const UPLOAD_LIMIT_MB = 10;
''', {
        "src/lib/session.ts": '''\
import { addMinutes } from "date-fns";
import { SESSION_TIMEOUT } from "@/lib/config";

export function sessionExpiry(now: Date): Date {
  return addMinutes(now, SESSION_TIMEOUT);
}

export function isExpired(expiresAt: Date, now = new Date()): boolean {
  return expiresAt <= now;
}
''',
        "src/lib/uploads.ts": '''\
import { UPLOAD_LIMIT_MB } from "@/lib/config";

export const tooBig = (bytes: number) => bytes > UPLOAD_LIMIT_MB * 1024 * 1024;
''',
    }),
    "cross-file-ts-sort-order": CrossFile("src/lib/invoices.ts", '''\
export interface Invoice {
  id: string;
  dueOn: string;
  totalCents: number;
  paid: boolean;
}

/** Unpaid invoices, soonest due first */
export function unpaidInvoices(invoices: Invoice[]): Invoice[] {
  return invoices.filter((i) => !i.paid).sort((a, b) => a.dueOn.localeCompare(b.dueOn));
}
''', '''\
export interface Invoice {
  id: string;
  dueOn: string;
  totalCents: number;
  paid: boolean;
}

/** Unpaid invoices, latest first, for the invoices list */
export function unpaidInvoices(invoices: Invoice[]): Invoice[] {
  return invoices.filter((i) => !i.paid).sort((a, b) => b.dueOn.localeCompare(a.dueOn));
}
''', {
        "src/components/next-payment.tsx": '''\
import { type Invoice, unpaidInvoices } from "@/lib/invoices";

export function NextPayment({ invoices }: { invoices: Invoice[] }) {
  const next = unpaidInvoices(invoices)[0]; // the one due soonest
  if (!next) return <p>Nothing to pay.</p>;
  return (
    <p>
      Next payment: {next.totalCents / 100} due {next.dueOn}
    </p>
  );
}
''',
        "src/app/invoices/page.tsx": '''\
import { unpaidInvoices } from "@/lib/invoices";
import { loadInvoices } from "@/lib/db";

export default async function InvoicesPage() {
  const invoices = unpaidInvoices(await loadInvoices());
  return <ul>{invoices.map((i) => <li key={i.id}>{i.dueOn}</li>)}</ul>;
}
''',
    }),
    "cross-file-js-sync-to-async": CrossFile("src/features/flags.js", '''\
import flagsFile from "../../flags.json";

export function loadFlags() {
  return { ...flagsFile.defaults, ...flagsFile[process.env.NODE_ENV] };
}
''', '''\
const FLAGS_URL = "https://flags.internal/api/flags";

export async function loadFlags() {
  const response = await fetch(FLAGS_URL);
  return response.json();
}
''', {
        "src/components/Dashboard.jsx": '''\
import { loadFlags } from "../features/flags";
import { NewDashboard } from "./NewDashboard";
import { OldDashboard } from "./OldDashboard";

export function Dashboard({ user }) {
  const flags = loadFlags();
  return flags.newDashboard ? <NewDashboard user={user} /> : <OldDashboard user={user} />;
}
''',
    }),
    "clean-cross-file-ts-optional-prop": CrossFile("src/components/button.tsx", '''\
type ButtonProps = { label: string; onClick: () => void };

export function Button({ label, onClick }: ButtonProps) {
  return <button onClick={onClick}>{label}</button>;
}
''', '''\
type ButtonProps = { label: string; onClick: () => void; size?: "sm" | "md" };

export function Button({ label, onClick, size = "md" }: ButtonProps) {
  return (
    <button className={size === "sm" ? "btn btn-sm" : "btn"} onClick={onClick}>
      {label}
    </button>
  );
}
''', {
        "src/app/settings/page.tsx": '''\
import { Button } from "@/components/button";

export default function Settings({ save }: { save: () => void }) {
  return <Button label="Save" onClick={save} />;
}
''',
        "src/components/toolbar.tsx": '''\
import { Button } from "./button";

export function Toolbar({ undo }: { undo: () => void }) {
  return <Button label="Undo" onClick={undo} size="sm" />;
}
''',
    }),

    # ---- clean: changes that look like they could break callers, and don't ----
    "clean-cross-file-optional-argument": CrossFile("notify/email.py", '''\
def send_email(smtp, to, subject, body):
    """Send a plain-text email"""
    message = f"To: {to}\\nSubject: {subject}\\n\\n{body}"
    smtp.sendmail("noreply@example.com", [to], message)
''', '''\
def send_email(smtp, to, subject, body, reply_to=None):
    """Send a plain-text email, with a Reply-To address if there's one"""
    headers = f"To: {to}\\nSubject: {subject}\\n"
    if reply_to:
        headers += f"Reply-To: {reply_to}\\n"
    smtp.sendmail("noreply@example.com", [to], f"{headers}\\n{body}")
''', {
        "notify/__init__.py": "",
        "shop/__init__.py": "",
        "shop/orders.py": '''\
from notify.email import send_email


def confirm(smtp, order):
    send_email(smtp, order.email, f"Order {order.id} confirmed", "Thanks for your order!")


def ask_for_review(smtp, order, support_address):
    send_email(smtp, order.email, "How was it?", "Reply and tell us.", reply_to=support_address)
''',
    }),
    "clean-cross-file-generator": CrossFile("reports/users.py", '''\
def active_users(db):
    """Every user who has logged in during the last 30 days"""
    return [row for row in db.query("SELECT * FROM users WHERE last_login > now() - interval '30 days'")]
''', '''\
def active_users(db):
    """Every user who has logged in during the last 30 days, a row at a time (there are millions)"""
    yield from db.stream("SELECT * FROM users WHERE last_login > now() - interval '30 days'")
''', {
        "reports/__init__.py": "",
        "reports/export.py": '''\
import csv

from reports.users import active_users


def export_active_users(db, out):
    """Write every active user to a CSV file"""
    writer = csv.writer(out)
    writer.writerow(["id", "email", "last_login"])
    for user in active_users(db):
        writer.writerow([user["id"], user["email"], user["last_login"]])
''',
    }),
}


if __name__ == "__main__":
    for name, text in SYNTHETIC.items():
        (CASES / f"{name}.diff").write_text(text)
        print(f"wrote {name}.diff")
    for name, case in CROSS_FILE.items():
        (CASES / f"{name}.diff").write_text(diff(case.path, case.before, case.after))
        repo = REPOS / name
        shutil.rmtree(repo, ignore_errors=True)
        for path, text in {**case.others, case.path: case.after}.items():
            (repo / path).parent.mkdir(parents=True, exist_ok=True)
            (repo / path).write_text(text)
        print(f"wrote {name}.diff and repos/{name}/")
