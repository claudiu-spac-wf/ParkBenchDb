"""Count model (data-model.md §2.3): the structure of a unit, drawn from the unit seed alone.

The planner uses structure_counts() to fix each unit's exact row counts (and so its ID ranges)
before any data exists; the generators replay the same structure to build the rows. Only
cardinalities and links are drawn here — no field values — so planning stays cheap.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from pbgen.generate import refdata
from pbgen.generate.common import HISTORY_MONTHS, binomial, poisson

# Per-account monthly rates, calibrated to feature 001's per-customer ratios at scale factor 1.
POS_PER_CARDED_ACCOUNT_MONTH = 2.7
OTHER_DEBITS_PER_ACCOUNT_MONTH = 0.89
OTHER_CREDITS_PER_ACCOUNT_MONTH = 0.67
TRANSFERS_PER_ACCOUNT_YEAR = 4.0
EXTRA_AUTH_P = {"PREAUTH": 0.44, "INCREMENT": 0.20, "REVERSAL": 0.24, "DECLINED": 0.12}

CUSTOMER_TABLES = ["Customer", "CustomerAddress", "CustomerContact", "CustomerDocument", "CustomerNote", "Account",
                   "AccountHolder", "Payee", "ScheduledPayment", "Card", "Loan", "LoanPayment", "AccountStatement",
                   "StatementDocument", "MonthlyBalance", "DebitTransaction", "CreditTransaction", "Transfer",
                   "CardAuthorization", "LoginEvent", "AuditLog"]
REFERENCE_TABLES = {"Currency": 40, "Country": 250, "ExchangeRate": 39 * 365, "Branch": 250, "AccountType": 24,
                    "InterestRateHistory": 24 * 120, "TransactionType": 60, "MerchantCategory": 600,
                    "BenchmarkTableInfo": 32}


@dataclass
class AccountPlan:
    owner: int                       # customer index within the unit
    type_id: int
    category: str
    open_month: int                  # 0 = opened before the window; k = opened in window month k
    months: list[int]                # active month indexes (0..11)
    activity: float
    holders: list[int] = field(default_factory=list)   # extra holder customer indexes
    n_sched: int = 0
    n_cards: int = 0
    stmt_doc: bool = False
    pos: list[int] = field(default_factory=list)       # per active month
    other_debits: list[int] = field(default_factory=list)
    other_credits: list[int] = field(default_factory=list)
    extras: list[dict] = field(default_factory=list)   # per active month: kind -> count


@dataclass
class LoanPlan:
    borrower: int
    account: int                     # account index (disbursement / payment account)
    n_payments: int
    window_months: list[int]         # months (0..11) whose payment is debited in the window


@dataclass
class CustomerPlan:
    kind: str
    lang: str
    n_addr: int
    contacts: list[str]
    n_docs: int
    n_notes: int
    n_payees: int
    paperless: bool
    n_logins: int
    n_audit: int
    accounts: list[int] = field(default_factory=list)


@dataclass
class UnitStructure:
    customers: list[CustomerPlan]
    accounts: list[AccountPlan]
    transfers: list[tuple[int, int, int]]      # (from account, to account, month)
    loans: list[LoanPlan]

    def counts(self) -> dict[str, int]:
        acc, cus = self.accounts, self.customers
        pos = sum(sum(a.pos) for a in acc)
        extras = sum(sum(sum(e.values()) for e in a.extras) for a in acc)
        loan_debits = sum(len(l.window_months) for l in self.loans)
        c = {
            "Customer": len(cus),
            "CustomerAddress": sum(x.n_addr for x in cus),
            "CustomerContact": sum(len(x.contacts) for x in cus),
            "CustomerDocument": sum(x.n_docs for x in cus),
            "CustomerNote": sum(x.n_notes for x in cus),
            "Account": len(acc),
            "AccountHolder": sum(1 + len(a.holders) for a in acc),
            "Payee": sum(x.n_payees for x in cus),
            "ScheduledPayment": sum(a.n_sched for a in acc),
            "Card": sum(a.n_cards for a in acc),
            "Loan": len(self.loans),
            "LoanPayment": sum(l.n_payments for l in self.loans),
            "AccountStatement": sum(len(a.months) for a in acc),
            "StatementDocument": sum(1 for a in acc if a.stmt_doc),
            "MonthlyBalance": sum(len(a.months) for a in acc),
            "DebitTransaction": pos + sum(sum(a.other_debits) for a in acc) + len(self.transfers) + loan_debits,
            "CreditTransaction": sum(sum(a.other_credits) for a in acc) + len(self.transfers),
            "Transfer": len(self.transfers),
            "CardAuthorization": pos + extras,
            "LoginEvent": sum(x.n_logins for x in cus),
            "AuditLog": sum(x.n_audit for x in cus),
        }
        return {t: n for t, n in c.items() if n > 0}


def _geometric(rng: random.Random, p: float, cap: int) -> int:
    n = 0
    while n < cap and rng.random() < p:
        n += 1
    return n


def customer_structure(seed: int, n_customers: int) -> UnitStructure:
    """Draws the structure of a customer unit. Deterministic for (seed, n_customers)."""
    rng = random.Random(seed)
    customers: list[CustomerPlan] = []
    accounts: list[AccountPlan] = []
    for ci in range(n_customers):
        kind = "I" if rng.random() < 0.92 else "B"
        lang = "es" if rng.random() < 0.12 else "en"
        contacts = ["EMAIL" if rng.random() < 0.3 else rng.choice(["MOBILE", "MOBILE", "HOME", "WORK"])
                    for _ in range(1 + binomial(rng, 4, 0.375))]
        c = CustomerPlan(kind=kind, lang=lang, n_addr=1 + binomial(rng, 2, 0.25), contacts=contacts,
                         n_docs=binomial(rng, 3, 1 / 3), n_notes=_geometric(rng, 0.6, 20),
                         n_payees=min(25, poisson(rng, 2.5)), paperless=rng.random() < 0.55,
                         n_logins=0 if rng.random() < 0.30 else poisson(rng, 17.14), n_audit=poisson(rng, 50))
        customers.append(c)
        for k in range(1 + binomial(rng, 3, 1 / 6)):
            r = rng.random()
            if k == 0 or r < 0.55:
                cat, type_id = "CHECKING", rng.choice(refdata.CHECKING_TYPE_IDS)
            elif r < 0.90:
                cat, type_id = "SAVINGS", rng.choice(refdata.SAVINGS_TYPE_IDS)
            else:
                type_id = rng.choice(refdata.OTHER_TYPE_IDS)
                cat = refdata.ACCOUNT_TYPES[type_id - 1][2]
            open_month = 0 if rng.random() < 0.9 else rng.randint(1, HISTORY_MONTHS - 1)
            a = AccountPlan(owner=ci, type_id=type_id, category=cat, open_month=open_month,
                            months=list(range(open_month, HISTORY_MONTHS)), activity=rng.gammavariate(1.2, 1 / 1.2))
            c.accounts.append(len(accounts))
            accounts.append(a)

    # holders, schedules, cards, statement documents, monthly counts
    for ai, a in enumerate(accounts):
        owner = customers[a.owner]
        others = [i for i in range(n_customers) if i != a.owner]
        for _ in range(binomial(rng, 3, 0.11)):
            if others:
                h = rng.choice(others)
                if h not in a.holders:
                    a.holders.append(h)
        a.n_sched = min(10, poisson(rng, 0.67)) if owner.n_payees else 0
        a.n_cards = min(3, poisson(rng, 0.95)) if a.category == "CHECKING" else 0
        a.stmt_doc = owner.paperless and rng.random() < 0.18
        for _ in a.months:
            pos = poisson(rng, POS_PER_CARDED_ACCOUNT_MONTH * a.activity) if a.n_cards else 0
            a.pos.append(pos)
            a.other_debits.append(poisson(rng, OTHER_DEBITS_PER_ACCOUNT_MONTH * a.activity))
            a.other_credits.append(poisson(rng, OTHER_CREDITS_PER_ACCOUNT_MONTH * a.activity))
            a.extras.append({k: binomial(rng, pos, p) for k, p in EXTRA_AUTH_P.items()} if pos else {})

    # transfers: counterparty inside the unit, active in the same month (60% same customer when possible)
    transfers: list[tuple[int, int, int]] = []
    for ai, a in enumerate(accounts):
        for _ in range(poisson(rng, TRANSFERS_PER_ACCOUNT_YEAR * len(a.months) / HISTORY_MONTHS)):
            month = rng.choice(a.months)
            own = [x for x in customers[a.owner].accounts if x != ai and month in accounts[x].months]
            pool = own if own and rng.random() < 0.6 else \
                [x for x in range(len(accounts)) if x != ai and month in accounts[x].months]
            if pool:
                transfers.append((ai, rng.choice(pool), month))

    # loans: payments debited from the borrower's first account during its active months
    loans: list[LoanPlan] = []
    for ci, c in enumerate(customers):
        for _ in range(binomial(rng, 3, 1 / 12)):
            acct = c.accounts[0]
            n_pay = rng.randint(1, 47)
            active = accounts[acct].months
            window = active[-min(n_pay, len(active)):] if n_pay else []
            loans.append(LoanPlan(borrower=ci, account=acct, n_payments=n_pay, window_months=window))
    return UnitStructure(customers=customers, accounts=accounts, transfers=transfers, loans=loans)


def customer_unit_counts(seed: int, n_customers: int) -> dict[str, int]:
    return customer_structure(seed, n_customers).counts()


def reference_unit_counts() -> dict[str, int]:
    return dict(REFERENCE_TABLES)
