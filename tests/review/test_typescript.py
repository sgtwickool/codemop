import pytest

from codemop.review.code import Block, language_for
from codemop.review.code.typescript import TYPESCRIPT
from codemop.review.context import build_context
from codemop.review.diff import parse_diff

LEDGER = '''\
import { formatCents } from "@/lib/money";

export interface Transfer {
  amountCents: number;
  note?: string;
}

export const RETRY_DELAY = 2000;

export function transfer(source: Account, target: Account, amount: number) {
  source.balance -= amount;
  target.balance += amount;
  return formatCents(amount);
}

export default class Ledger {
  entries: Transfer[] = [];
  add = (entry: Transfer) => {
    this.entries.push(entry);
  };
  total() {
    return this.entries.reduce((sum, e) => sum + e.amountCents, 0);
  }
}
'''

PAGE = '''\
import Ledger, { transfer as move } from "../lib/ledger";
import * as money from "@/lib/money";

export const Checkout = ({ invoice, customer, shop }: Props) => {
  const onPay = () => {
    move(invoice.total, customer.account, shop.account);
  };
  return <PayButton onClick={onPay} label={money.formatCents(invoice.total)} />;
};
'''


def parsed(text, path="src/lib/ledger.ts"):
    return TYPESCRIPT.parse(path, text)


def test_typescript_and_javascript_files_are_read():
    for path in ("a.ts", "a.tsx", "a.js", "a.jsx", "a.mjs", "a.cjs"):
        assert language_for(path) is TYPESCRIPT
    assert language_for("a.go") is None


def test_the_named_function_or_class_around_a_line():
    code = parsed(LEDGER)

    assert code.innermost(11) == Block(10, 14, "function", "transfer")
    assert code.innermost(19) == Block(18, 20, "method", "add")  # an arrow function held in a field
    assert code.innermost(22) == Block(21, 23, "method", "total")  # not the anonymous callback inside it
    assert code.innermost(8) is None


def test_a_component_held_in_a_const_is_a_function():
    assert parsed(PAGE, "src/app/checkout.tsx").innermost(8) == Block(4, 9, "function", "Checkout")


def test_what_a_change_defines_with_what_has_to_be_imported_to_use_it():
    code = parsed(LEDGER)

    assert code.changed_definitions({11}) == {"transfer": "transfer"}
    assert code.changed_definitions({8}) == {"RETRY_DELAY": "RETRY_DELAY"}
    assert code.changed_definitions({4}) == {"Transfer": "Transfer", "amountCents": "Transfer"}  # a renamed field
    assert code.changed_definitions({22}) == {"total": "Ledger"}


def test_top_level_definitions_including_the_default_export():
    definitions = parsed(LEDGER).top_level_definitions()

    assert {"Transfer", "RETRY_DELAY", "transfer", "Ledger", "default"} <= set(definitions)
    assert definitions["default"] == definitions["Ledger"]
    assert (definitions["transfer"].start, definitions["transfer"].end) == (10, 14)


def test_imports_and_what_comes_from_a_module():
    code = parsed(PAGE, "src/app/checkout.tsx")

    assert code.imports() == {"Ledger": ("default", "../lib/ledger"), "move": ("transfer", "../lib/ledger"),
                              "money": ("*", "@/lib/money")}
    assert code.imported_from("ledger") == {"default", "Ledger", "transfer"}
    assert code.imported_from("money") == {"*"}
    assert code.imported_from("other") == set()


def test_references_by_name_property_type_and_jsx_tag_but_not_in_imports():
    code = parsed(PAGE, "src/app/checkout.tsx")

    assert code.references({"move", "PayButton", "formatCents", "account"}) == [
        (6, "account"), (6, "account"), (6, "move"), (8, "PayButton"), (8, "formatCents")]


def test_where_an_import_comes_from():
    repo = {"src/lib/ledger.ts", "src/lib/money/index.ts", "src/app/checkout.tsx", "src/lib/util.ts"}

    assert TYPESCRIPT.module_paths("../lib/ledger", "src/app/checkout.tsx", repo) == ["src/lib/ledger.ts"]
    assert TYPESCRIPT.module_paths("@/lib/money", "src/app/checkout.tsx", repo) == ["src/lib/money/index.ts"]
    assert TYPESCRIPT.module_paths("./util.js", "src/lib/ledger.ts", repo) == ["src/lib/util.ts"]  # ESM
    assert TYPESCRIPT.module_paths("react", "src/app/checkout.tsx", repo) == []  # from node_modules
    assert TYPESCRIPT.module_name("src/lib/money/index.ts") == "money"


class Files:
    def __init__(self, files):
        self.files = files

    async def read(self, path):
        return self.files.get(path)

    async def paths(self):
        return list(self.files)


@pytest.mark.asyncio
async def test_context_for_a_typescript_change_finds_its_callers_in_other_files():
    """transfer's arguments are reordered; the checkout page, which imports it under another name, still
    passes the amount first"""
    diff = ("diff --git a/src/lib/ledger.ts b/src/lib/ledger.ts\n--- a/src/lib/ledger.ts\n+++ b/src/lib/ledger.ts\n"
            "@@ -9,4 +9,4 @@\n \n-export function transfer(amount: number, source: Account, target: Account) {\n"
            "+export function transfer(source: Account, target: Account, amount: number) {\n"
            "   source.balance -= amount;\n   target.balance += amount;\n")
    files = Files({"src/lib/ledger.ts": LEDGER, "src/app/checkout.tsx": PAGE.replace("move(", "transfer(").replace(
        "transfer as move", "transfer"), "src/lib/money.ts": "export function formatCents(c: number) {\n  return c;\n}\n"})

    context = await build_context(parse_diff(diff), files)

    headings = [line for line in context.splitlines() if line.startswith("#### ")]
    assert headings == [
        "#### src/lib/ledger.ts, lines 10-14 (function transfer)",
        "#### src/app/checkout.tsx, lines 5-7 (uses transfer)",
        "#### src/lib/money.ts, lines 1-3 (defines formatCents)",  # through the "@/lib/money" alias
    ]
    assert "  6 |     transfer(invoice.total, customer.account, shop.account);" in context
