"""CUSTOMER unit: a block of customers with every dependent table (data-model.md §5).

The unit replays counts.customer_structure() — the same draws the planner used — so the row
counts always equal the unit's planned RowCounts. All balances, statements and links are
derived from one chronological transaction stream per account, so the documented rules
(statement totals, running balances, transfer/loan/card links) hold by construction.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import math
import random

from pbgen import counts as cm
from pbgen.generate import lob, refdata
from pbgen.generate.common import (TZ, RowFactory, RunContext, Weighted, _parse_map, bijective_number, cents,
                                   merchant_name, money, rand_datetime, rand_day, seed_int, zipf_index)
from pbgen.generate.fakerpool import UnitFakers, fit_bytes, pool, sized_text

W_STATUS = Weighted([("ACTIVE", 90), ("DORMANT", 7), ("CLOSED", 3)])
W_SEGMENT = Weighted([("RETAIL", 80), ("PREMIER", 12), ("PRIVATE", 2), ("SMB", 6)])
W_RISK = Weighted([("L", 80), ("M", 17), ("H", 3)])
W_ACCT_STATUS = Weighted([("OPEN", 92), ("DORMANT", 5), ("FROZEN", 0.5), ("CLOSED", 2.5)])
W_CARD_KIND = Weighted([("DEBIT", 85), ("CREDIT", 12), ("PREPAID", 3)])
W_CARD_STATUS = Weighted([("ACTIVE", 88), ("LOCKED", 2), ("EXPIRED", 6), ("CANCELLED", 4)])
W_NETWORK = Weighted([("VISA", 50), ("MC", 35), ("AMEX", 10), ("DISCOVER", 5)])
W_HOLDER = Weighted([("JOINT", 60), ("AUTHORIZED", 30), ("TRUSTEE", 10)])
W_FREQ = Weighted([("ONCE", 10), ("WEEKLY", 10), ("BIWEEKLY", 15), ("MONTHLY", 55), ("QUARTERLY", 10)])
W_SCHED_STATUS = Weighted([("ACTIVE", 70), ("PAUSED", 5), ("CANCELLED", 15), ("COMPLETED", 10)])
W_LOAN_KIND = Weighted([("MORTGAGE", 25), ("AUTO", 35), ("PERSONAL", 25), ("STUDENT", 10), ("HELOC", 5)])
W_LOAN_STATUS = Weighted([("CURRENT", 90), ("LATE", 5), ("DEFAULT", 1), ("PAIDOFF", 4)])
W_DOC_KIND = Weighted([("PASSPORT", 25), ("DRIVERLIC", 40), ("UTILITYBILL", 15), ("TAXFORM", 15), ("OTHER", 5)])
W_DOC_STATUS = Weighted([("VERIFIED", 90), ("PENDING", 7), ("REJECTED", 3)])
W_NOTE_KIND = Weighted([("CALL", 35), ("EMAIL", 25), ("BRANCH", 20), ("COMPLAINT", 5), ("SYSTEM", 15)])
W_LOGIN = Weighted([("LOGIN", 70), ("FAILED", 8), ("MFA", 12), ("LOGOUT", 10)])
W_AUDIT_TABLE = Weighted([("Account", 40), ("Customer", 35), ("Card", 25)])
W_AUDIT_ACTION = Weighted([("C", 20), ("U", 75), ("D", 5)])
W_ENTRY = Weighted([("CHIP", 40), ("SWIP", 10), ("TAP", 30), ("ECOM", 20)])
W_DECLINE = Weighted([("05", 40), ("51", 35), ("54", 10), ("61", 15)])
W_OTHER_DEBIT = Weighted(refdata.OTHER_DEBIT_TYPES)
W_POS = Weighted(refdata.POS_TYPES)
W_OTHER_CREDIT = Weighted(refdata.OTHER_CREDIT_TYPES)
TT_DESC = {t[0]: t[1] for t in refdata.TRANSACTION_TYPES}
SECURITY_QUESTIONS = ["What was your first pet's name?", "What city were you born in?", "What is your mother's maiden name?",
                      "What was your first car?", "What was the name of your primary school?",
                      "What is your favorite book?", "What was your childhood nickname?", "Where did you meet your spouse?",
                      "What is the name of your favorite teacher?", "What street did you grow up on?"]
LOAN_RANGES = {"MORTGAGE": (80000, 1500000, 180, 360), "AUTO": (5000, 90000, 36, 84), "PERSONAL": (2000, 40000, 12, 60),
               "STUDENT": (5000, 120000, 60, 240), "HELOC": (10000, 250000, 60, 240)}
OPENING = {"CHECKING": 2500, "SAVINGS": 8000, "MONEYMARKET": 20000, "CD": 10000}


def _lognormal(rng: random.Random, median: float, sigma: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, math.exp(rng.gauss(math.log(median), sigma))))


def _add_months(d: dt.date, months: int, day: int = 15) -> dt.date:
    y, m = divmod(d.year * 12 + d.month - 1 + months, 12)
    return dt.date(y, m + 1, min(day, 28))


def _debit_amount(rng: random.Random, code: str) -> float:
    if code.startswith("FEE"):
        return round(rng.uniform(2, 35), 2)
    if code.startswith("ATM") or code == "CASHWD":
        return float(rng.randint(1, 20) * 20)
    if code.startswith("WIRE"):
        return round(rng.uniform(500, 10000), 2)
    if code == "CHKPAID":
        return round(_lognormal(rng, 150, 1.0, 20, 2000), 2)
    return round(_lognormal(rng, 120, 0.9, 10, 3000), 2)


class _Stream:
    """One account's transaction events; turned into rows in chronological order."""

    __slots__ = ("events",)

    def __init__(self):
        self.events: list[tuple] = []  # (when, seq, kind, amount_cents, info)


def generate_customer_unit(unit: dict, ctx: RunContext) -> dict[str, list[dict]]:
    seed = int(unit["UnitSeed"], 16)
    first = _parse_map(unit["FirstIds"])
    planned = _parse_map(unit["RowCounts"])
    n = planned["Customer"]
    st = cm.customer_structure(seed, n)
    rng = random.Random(seed_int(seed, "values"))
    rows = RowFactory(ctx.schema, random.Random(seed_int(seed, "randomint")))
    fakers = UnitFakers(seed)
    fk = fakers.en
    next_id = dict(first)

    def nid(table: str) -> int:
        v = next_id[table]
        next_id[table] = v + 1
        return v

    months = ctx.months
    win_start = months[0][0]
    emp_max = max(1, ctx.employee_max)
    mer_max = max(1, ctx.merchant_max)
    payer_pool = pool(fk, "company", 64)
    memo_pool = [fk.sentence(nb_words=5)[:60] for _ in range(32)]

    cust_ids = [first["Customer"] + i for i in range(n)]
    acct_ids = [first["Account"] + i for i in range(len(st.accounts))] if st.accounts else []

    # ------------------------------------------------------------------ customers
    cinfo = []
    for ci, cp in enumerate(st.customers):
        f = fakers.get(cp.lang)
        cid = cust_ids[ci]
        is_biz = cp.kind == "B"
        since = win_start - dt.timedelta(days=rng.randint(60, 45 * 365))
        created = dt.datetime.combine(since, dt.time(10, 0), TZ)
        first_name = "" if is_biz else f.first_name()
        last_name = f.last_name()
        branch = zipf_index(rng, ctx.branch_count, 0.9)
        prefs = ";".join(f"{k}={fk.word()}" for k in ("theme", "lang", "alerts", "stmt", "home", "tips", "mfa",
                                                     "channel", "digest", "promo", "region", "device", "sort",
                                                     "limit", "tone", "font", "layout", "widget"))
        prefs = prefs[:rng.randint(150, 300)]
        cinfo.append({"id": cid, "since": since, "branch": branch, "first": first_name, "last": last_name,
                      "payees": [], "paperless": cp.paperless})
        rows.add("Customer", cid, created, CustomerNumber=f"C{bijective_number(cid, 10, 12345):010d}",
                 CustomerKind=cp.kind, FirstName=first_name[:30],
                 MiddleName=f.first_name()[:30] if (not is_biz and rng.random() < 0.4) else "",
                 LastName=last_name[:40], BusinessName=f.company()[:80] if is_biz else "",
                 DateOfBirth=None if is_biz else ctx.as_of - dt.timedelta(days=rng.randint(18 * 365, 95 * 365)),
                 TaxIdMasked=f"***-**-{rng.randint(0, 9999):04d}", Email=f.email()[:80],
                 PreferredLanguage="es" if cp.lang == "es" else ("en" if rng.random() < 0.97 else "fr"),
                 HomeBranchId=branch, Segment="SMB" if is_biz else W_SEGMENT.pick(rng),
                 CreditScore=max(300, min(850, int(rng.gauss(700, 60)))),
                 AnnualIncome=round(_lognormal(rng, 65000, 0.6, 12000, 5_000_000), 2),
                 CustomerSince=since, CustomerStatus=W_STATUS.pick(rng), IsPaperless=cp.paperless,
                 MarketingOptIn=rng.random() < 0.35,
                 KycVerifiedAt=created + dt.timedelta(days=rng.randint(0, 30)) if rng.random() < 0.98 else None,
                 RiskRating=W_RISK.pick(rng), Occupation=f.job()[:40], EmployerName=f.company()[:60],
                 SecurityQuestion=rng.choice(SECURITY_QUESTIONS), Preferences=prefs,
                 LastContactDate=rand_day(rng, win_start, ctx.as_of) if rng.random() < 0.7 else None)

        for k in range(cp.n_addr):
            kind = "HOME" if k == 0 else rng.choice(["MAILING", "WORK"])
            country = "US" if rng.random() < 0.95 else rng.choice(["CA", "MX", "GB", "ES"])
            valid_to = (ctx.as_of - dt.timedelta(days=rng.randint(30, 900))) if (k > 0 and rng.random() < 0.3) else None
            rows.add("CustomerAddress", nid("CustomerAddress"), created, CustomerId=cid, AddressKind=kind,
                     AddressLine1=f.street_address()[:60], AddressLine2=f.secondary_address()[:60] if rng.random() < 0.2 else "",
                     City=f.city()[:40], StateProvince=f.state()[:30], PostalCode=f.postcode()[:10],
                     CountryCode=country, IsPrimary=k == 0, ValidFrom=since, ValidTo=valid_to)

        seen_kinds = set()
        for kind in cp.contacts:
            verified = rng.random() < 0.85
            rows.add("CustomerContact", nid("CustomerContact"), created, CustomerId=cid, ContactKind=kind,
                     ContactValue=(f.email() if kind == "EMAIL" else f.phone_number())[:80],
                     IsPrimary=kind not in seen_kinds, IsVerified=verified,
                     VerifiedAt=created + dt.timedelta(days=rng.randint(0, 60)) if verified else None)
            seen_kinds.add(kind)

        for _ in range(cp.n_docs):
            kind = W_DOC_KIND.pick(rng)
            mime = rng.choice(["image/jpeg", "image/png", "application/pdf"])
            content = lob.binary_doc(rng, mime, 4096, 16384, 65536) if rng.random() < 0.10 else None
            issued = since + dt.timedelta(days=rng.randint(0, 3000))
            expires = issued + dt.timedelta(days=rng.randint(365 * 4, 365 * 10)) if kind in ("PASSPORT", "DRIVERLIC") else None
            rows.add("CustomerDocument", nid("CustomerDocument"), created, CustomerId=cid, DocumentKind=kind,
                     DocumentNumberMasked=f"****{rng.randint(0, 999999):06d}", IssuingCountryCode="US",
                     IssueDate=issued, ExpiryDate=expires, VerificationStatus=W_DOC_STATUS.pick(rng),
                     VerifiedByEmployeeId=rng.randint(1, emp_max), MimeType=mime,
                     FileName=f"{kind.lower()}_{cid}.{'pdf' if mime.endswith('pdf') else mime.split('/')[1]}",
                     FileSizeBytes=len(content) if content else 0, Content=content)

        for _ in range(cp.n_notes):
            when = rand_datetime(rng, ctx.as_of - dt.timedelta(days=rng.randint(0, 5 * 365)))
            size = lob.target_size(rng, 200, 1200, 8192)
            text = fit_bytes(sized_text(f, rng, size, size), 8192) if rng.random() < 0.6 else None
            rows.add("CustomerNote", nid("CustomerNote"), when, CustomerId=cid, EmployeeId=rng.randint(1, emp_max),
                     NoteKind=W_NOTE_KIND.pick(rng), NoteDateTime=when, Summary=sized_text(f, rng, 80, 300),
                     NoteText=text, FollowUpDate=(when.date() + dt.timedelta(days=rng.randint(1, 30))) if rng.random() < 0.15 else None,
                     IsResolved=rng.random() < 0.85)

        for _ in range(cp.n_payees):
            pid = nid("Payee")
            cinfo[ci]["payees"].append(pid)
            kind = rng.choice(["BILLER", "BILLER", "PERSON", "BUSINESS"])
            rows.add("Payee", pid, created + dt.timedelta(days=rng.randint(0, 400)), CustomerId=cid,
                     PayeeName=(f.name() if kind == "PERSON" else f.company())[:80], PayeeKind=kind,
                     BankRoutingNumber=f"{rng.randint(10000000, 399999999):09d}",
                     AccountNumberMasked=f"****{rng.randint(0, 9999):04d}", ReferenceText=f.bothify("??####-####")[:40],
                     Email=f.email()[:80] if rng.random() < 0.4 else "", AddressLine1=f.street_address()[:60],
                     City=f.city()[:40], PostalCode=f.postcode()[:10], IsFavorite=rng.random() < 0.2,
                     LastPaidDate=rand_day(rng, win_start, ctx.as_of) if rng.random() < 0.8 else None)

    # ------------------------------------------------------------------ account plan: ids, dates, openings
    ainfo = []
    for ai, ap in enumerate(st.accounts):
        c = cinfo[ap.owner]
        if ap.open_month == 0:
            open_date = c["since"] + dt.timedelta(days=rng.randint(0, max(1, (win_start - c["since"]).days - 1)))
        else:
            mfirst, mlast = months[ap.open_month]
            open_date = rand_day(rng, mfirst, mlast)
        opening = cents(_lognormal(rng, OPENING[ap.category], 1.0, 50, 2_000_000))
        ainfo.append({"id": acct_ids[ai], "open": open_date, "opening": opening, "stream": _Stream(),
                      "cards": [], "stmt": {}, "type": refdata.ACCOUNT_TYPES[ap.type_id - 1]})

    # statement ids per (account, month)
    for ai, ap in enumerate(st.accounts):
        for mo in ap.months:
            ainfo[ai]["stmt"][mo] = nid("AccountStatement")

    # cards (ids needed by POS authorizations)
    for ai, ap in enumerate(st.accounts):
        holders = [ap.owner] + ap.holders
        for _ in range(ap.n_cards):
            ainfo[ai]["cards"].append((nid("Card"), holders[rng.randrange(len(holders))]))

    # ------------------------------------------------------------------ events per account
    seq = 0
    for ai, ap in enumerate(st.accounts):
        s = ainfo[ai]["stream"]
        for k, mo in enumerate(ap.months):
            mfirst, mlast = months[mo]
            if mo == ap.open_month and ap.open_month:
                mfirst = ainfo[ai]["open"]
            for _ in range(ap.pos[k]):
                seq += 1
                s.events.append((rand_datetime(rng, rand_day(rng, mfirst, mlast)), seq, "POS",
                                 cents(_lognormal(rng, 35, 0.9, 1, 2500)), {"type": W_POS.pick(rng),
                                 "merchant": zipf_index(rng, mer_max, 1.05), "month": mo}))
            for _ in range(ap.other_debits[k]):
                seq += 1
                code = W_OTHER_DEBIT.pick(rng)
                s.events.append((rand_datetime(rng, rand_day(rng, mfirst, mlast)), seq, "DEBIT",
                                 cents(_debit_amount(rng, code)), {"type": code, "month": mo}))
            for _ in range(ap.other_credits[k]):
                seq += 1
                payroll = rng.random() < 0.6
                code = "PAYROLL" if payroll else W_OTHER_CREDIT.pick(rng)
                amt = rng.uniform(1000, 8000) if payroll else _lognormal(rng, 150, 1.0, 5, 20000)
                s.events.append((rand_datetime(rng, rand_day(rng, mfirst, mlast)), seq, "CREDIT", cents(amt),
                                 {"type": code, "payroll": payroll, "month": mo}))

    transfer_links = []
    for ti, (fa, ta, mo) in enumerate(st.transfers):
        mfirst, mlast = months[mo]
        lo = max(mfirst, ainfo[fa]["open"], ainfo[ta]["open"])
        when = rand_datetime(rng, rand_day(rng, lo, mlast) if lo <= mlast else mlast)
        amt = cents(_lognormal(rng, 400, 1.0, 20, 25000))
        seq += 1
        ainfo[fa]["stream"].events.append((when, seq, "XFER_OUT", amt, {"transfer": ti, "month": mo}))
        seq += 1
        ainfo[ta]["stream"].events.append((when + dt.timedelta(seconds=1), seq, "XFER_IN", amt, {"transfer": ti, "month": mo}))
        transfer_links.append({"from": fa, "to": ta, "when": when, "amount": amt})

    loan_info = []
    for li, lp in enumerate(st.loans):
        kind = W_LOAN_KIND.pick(rng)
        lo_amt, hi_amt, lo_term, hi_term = LOAN_RANGES[kind]
        principal = round(rng.uniform(lo_amt, hi_amt), 2)
        term = max(lp.n_payments + 1, rng.randint(lo_term, hi_term))
        rate = round(rng.uniform(2.5, 24.0) if kind in ("PERSONAL",) else rng.uniform(2.5, 12.0), 4)
        r = rate / 1200
        payment = round(principal * r / (1 - (1 + r) ** -term), 2)
        last_due = _add_months(months[-1][0], 0)
        loan_info.append({"kind": kind, "principal": principal, "term": term, "rate": rate, "payment": payment,
                          "last_due": last_due, "debits": {}})
        for k, mo in enumerate(lp.window_months):
            due = dt.date(months[mo][0].year, months[mo][0].month, 15)
            when = rand_datetime(rng, min(months[mo][1], max(due, ainfo[lp.account]["open"]) + dt.timedelta(days=rng.randint(-3, 5))), False)
            seq += 1
            ainfo[lp.account]["stream"].events.append((when, seq, "LOANPMT", cents(payment), {"loan": li, "month": mo}))

    # ------------------------------------------------------------------ transactions, statements, balances
    debit_by_event: dict[int, int] = {}
    xfer_debit, xfer_credit = {}, {}
    pos_debits = []  # (account index, debit id, when, amount, merchant)
    for ai, ap in enumerate(st.accounts):
        a = ainfo[ai]
        events = sorted(a["stream"].events, key=lambda e: (e[0], e[1]))
        # deposit accounts never run below zero: an account whose debits outrun its credits in the
        # window must have started with more money (row counts stay as planned)
        low = run = 0
        for _, _, kind, amt, _ in events:
            run += -amt if kind in ("POS", "DEBIT", "XFER_OUT", "LOANPMT") else amt
            low = min(low, run)
        if a["opening"] + low < 0:
            a["opening"] = -low + 2_500 + (-low) // 20      # plus a $25 + 5% cushion
        bal = a["opening"]
        by_month: dict[int, list] = {mo: [] for mo in ap.months}
        for when, eseq, kind, amt, info in events:
            mo = info["month"]
            sid = a["stmt"][mo]
            if kind in ("POS", "DEBIT", "XFER_OUT", "LOANPMT"):
                bal -= amt
                did = nid("DebitTransaction")
                if kind == "POS":
                    code, merchant = info["type"], info["merchant"]
                    desc = merchant_name(ctx.base_seed, merchant)[:60]
                    pos_debits.append((ai, did, when, amt, merchant))
                elif kind == "DEBIT":
                    code, merchant, desc = info["type"], 0, TT_DESC[info["type"]][:60]
                elif kind == "XFER_OUT":
                    code, merchant, desc = "XFER", 0, "Transfer to another account"
                    xfer_debit[info["transfer"]] = did
                else:
                    code, merchant, desc = "LOANPMT", 0, "Loan payment"
                    loan_info[info["loan"]]["debits"][mo] = (did, when)
                rows.add("DebitTransaction", did, when, AccountId=a["id"], TransactionTypeId=refdata.TT_ID[code],
                         AccountStatementId=sid, MerchantId=merchant, PostedDate=when.date(), PostedAt=when,
                         Amount=money(amt), RunningBalance=money(bal), Description=desc,
                         ReferenceNumber=f"D{did:019d}"[-20:], CheckNumber=rng.randint(1000, 999999) if code == "CHKPAID" else 0)
                by_month[mo].append(("D", when, amt, bal, code))
            else:
                bal += amt
                crid = nid("CreditTransaction")
                if kind == "XFER_IN":
                    code, payroll, payer, desc = "XFERIN", False, cinfo[ap.owner]["last"], "Transfer from another account"
                    xfer_credit[info["transfer"]] = crid
                else:
                    code, payroll = info["type"], info["payroll"]
                    payer = rng.choice(payer_pool)
                    desc = TT_DESC[code]
                rows.add("CreditTransaction", crid, when, AccountId=a["id"], TransactionTypeId=refdata.TT_ID[code],
                         AccountStatementId=sid, PostedDate=when.date(), PostedAt=when, Amount=money(amt),
                         RunningBalance=money(bal), Description=desc[:60], PayerName=payer[:60],
                         ReferenceNumber=f"C{crid:019d}"[-20:], IsPayroll=payroll)
                by_month[mo].append(("C", when, amt, bal, code))
        a["current"] = bal
        a["last_activity"] = events[-1][0] if events else None

        # statements and monthly balances
        prev_close = a["opening"]
        latest_sid = None
        for mo in ap.months:
            mfirst, mlast = months[mo]
            items = by_month[mo]
            debits = sum(x[2] for x in items if x[0] == "D")
            credits = sum(x[2] for x in items if x[0] == "C")
            close = prev_close - debits + credits
            sid = a["stmt"][mo]
            generated = dt.datetime.combine(mlast + dt.timedelta(days=1), dt.time(rng.randint(2, 4), rng.randint(0, 59)), TZ)
            notice = fit_bytes(sized_text(fk, rng, 512, 4096), 4096) if rng.random() < 0.01 else None
            rows.add("AccountStatement", sid, generated, AccountId=a["id"], PeriodStart=mfirst, PeriodEnd=mlast,
                     OpeningBalance=money(prev_close), ClosingBalance=money(close), TotalDebits=money(debits),
                     TotalCredits=money(credits), DebitCount=sum(1 for x in items if x[0] == "D"),
                     CreditCount=sum(1 for x in items if x[0] == "C"),
                     InterestEarned=money(sum(x[2] for x in items if x[4] == "INTPAID")),
                     FeesCharged=money(sum(x[2] for x in items if x[4].startswith("FEE"))),
                     DeliveryMethod="EMAIL" if cinfo[ap.owner]["paperless"] else "PAPER",
                     GeneratedAt=generated, NoticeText=notice)
            # daily balances for the month
            day_bal, low, high, overdrawn, total = prev_close, prev_close, prev_close, 0, 0
            ndays = (mlast - mfirst).days + 1
            it = iter(items)
            nxt = next(it, None)
            for d in range(ndays):
                day = mfirst + dt.timedelta(days=d)
                while nxt is not None and nxt[1].date() <= day:
                    day_bal = nxt[3]
                    low, high = min(low, day_bal), max(high, day_bal)
                    nxt = next(it, None)
                total += day_bal
                overdrawn += day_bal < 0
            rows.add("MonthlyBalance", nid("MonthlyBalance"), generated, AccountId=a["id"], BalanceMonth=mfirst,
                     OpeningBalance=money(prev_close), ClosingBalance=money(close), MinimumBalance=money(low),
                     MaximumBalance=money(high), AverageDailyBalance=money(total // ndays), TotalDebits=money(debits),
                     TotalCredits=money(credits), DebitCount=sum(1 for x in items if x[0] == "D"),
                     CreditCount=sum(1 for x in items if x[0] == "C"), DaysOverdrawn=overdrawn)
            prev_close = close
            latest_sid = (sid, generated)
        if ap.stmt_doc and latest_sid:
            sid, generated = latest_sid
            pdf = lob.pdf_like(rng, 3072, 8192, 32768, f"Statement {sid}")
            xml_len = lob.target_size(rng, 1024, 3072, 8192)
            xml = f'<statement id="{sid}" account="{a["id"]}"><lines>' + \
                  "".join(f"<l>{fk.word()}</l>" for _ in range(max(1, xml_len // 12)))
            xml = fit_bytes(xml[:xml_len - 22] if len(xml) > xml_len - 22 else xml, 8192 - 22) + "</lines></statement>"
            rows.add("StatementDocument", nid("StatementDocument"), generated, AccountStatementId=sid,
                     DocumentFormat="PDF", PageCount=rng.randint(1, 6), Checksum=hashlib.sha256(pdf).hexdigest(),
                     RenderedAt=generated + dt.timedelta(minutes=rng.randint(1, 90)), PdfContent=pdf, StatementXml=xml)

    # ------------------------------------------------------------------ accounts, holders, schedules, cards
    for ai, ap in enumerate(st.accounts):
        a = ainfo[ai]
        c = cinfo[ap.owner]
        code, name, cat, term, rate, minbal, fee, od = a["type"]
        status = W_ACCT_STATUS.pick(rng)
        created = dt.datetime.combine(a["open"], dt.time(11, 0), TZ)
        rows.add("Account", a["id"], created, AccountNumber=f"{bijective_number(a['id'], 12, 98765):012d}"
                 f"{bijective_number(a['id'], 12, 98765) % 97:02d}", AccountTypeId=ap.type_id, BranchId=c["branch"],
                 CurrencyCode="USD" if rng.random() < 0.97 else rng.choice(["EUR", "CAD", "MXN", "GBP"]),
                 AccountStatus=status, OpenDate=a["open"], CloseDate=ctx.as_of if status == "CLOSED" else None,
                 CurrentBalance=money(a["current"]), AvailableBalance=money(a["current"] - cents(rng.uniform(0, 50))),
                 OverdraftLimit=float(rng.choice([0, 0, 250, 500, 1000])) if od else 0.0,
                 InterestRate=round(rate, 4), Nickname=fk.word().title()[:40] if rng.random() < 0.3 else "",
                 LastStatementDate=months[ap.months[-1]][1] if ap.months else None,
                 LastActivityAt=a["last_activity"], UpdatedAt=a["last_activity"] or created)
        holders = [ap.owner] + ap.holders
        roles = ["PRIMARY"] + [W_HOLDER.pick(rng) for _ in ap.holders]
        owners = [i for i, r in enumerate(roles) if r in ("PRIMARY", "JOINT")]
        share = 10000 // len(owners)
        for i, (h, role) in enumerate(zip(holders, roles)):
            pct = (share + 10000 - share * len(owners)) if i == 0 else (share if role == "JOINT" else 0)
            rows.add("AccountHolder", nid("AccountHolder"), created, AccountId=a["id"], CustomerId=cinfo[h]["id"],
                     HolderRole=role, OwnershipPercent=pct / 100, AddedDate=a["open"])
        payees = c["payees"]
        for _ in range(ap.n_sched):
            freq, pstatus = W_FREQ.pick(rng), W_SCHED_STATUS.pick(rng)
            runs = rng.randint(0, 40)
            rows.add("ScheduledPayment", nid("ScheduledPayment"), created, AccountId=a["id"], PayeeId=rng.choice(payees),
                     Amount=round(rng.uniform(10, 5000), 2), Frequency=freq,
                     NextRunDate=(ctx.as_of + dt.timedelta(days=rng.randint(1, 30))) if pstatus == "ACTIVE" else None,
                     EndDate=(ctx.as_of + dt.timedelta(days=rng.randint(30, 900))) if rng.random() < 0.3 else None,
                     Memo=rng.choice(memo_pool), PaymentStatus=pstatus, RunCount=runs,
                     LastRunAt=rand_datetime(rng, rand_day(rng, win_start, ctx.as_of)) if runs else None)
        for card_id, holder in a["cards"]:
            issued = max(a["open"], ctx.as_of - dt.timedelta(days=rng.randint(30, 1400)))
            rows.add("Card", card_id, dt.datetime.combine(issued, dt.time(12, 0), TZ),
                     CardToken=hashlib.sha256(f"{ctx.base_seed}:card:{card_id}".encode()).hexdigest()[:32],
                     CardNumberMasked=f"**** **** **** {rng.randint(0, 9999):04d}", AccountId=a["id"],
                     CustomerId=cinfo[holder]["id"], CardKind=W_CARD_KIND.pick(rng), Network=W_NETWORK.pick(rng),
                     EmbossedName=f"{cinfo[holder]['first']} {cinfo[holder]['last']}".strip().upper()[:26],
                     ExpiryMonth=rng.randint(1, 12), ExpiryYear=issued.year + rng.randint(2, 5), IssueDate=issued,
                     CardStatus=W_CARD_STATUS.pick(rng), DailyLimit=float(rng.choice([500, 1000, 2500, 5000, 10000])),
                     IsContactless=rng.random() < 0.9)

    # ------------------------------------------------------------------ transfers
    for ti, t in enumerate(transfer_links):
        rows.add("Transfer", nid("Transfer"), t["when"], FromAccountId=ainfo[t["from"]]["id"],
                 ToAccountId=ainfo[t["to"]]["id"], Amount=money(t["amount"]), TransferDateTime=t["when"],
                 DebitTransactionId=xfer_debit[ti], CreditTransactionId=xfer_credit[ti], TransferStatus="POSTED",
                 Channel=rng.choice(["ONLINE", "MOBILE", "BRANCH"]))

    # ------------------------------------------------------------------ card authorizations
    def auth(card_id, merchant, when, amount_c, kind, debit_id, approved):
        rows.add("CardAuthorization", nid("CardAuthorization"), when, CardId=card_id, MerchantId=merchant,
                 AuthDateTime=when, MerchantLocalDateTime=when.replace(tzinfo=None), Amount=money(amount_c),
                 CurrencyCode="USD" if rng.random() < 0.95 else rng.choice(["EUR", "CAD", "GBP", "MXN"]),
                 AuthCode=fk.bothify("??####").upper() if approved else "", ResponseCode="00" if approved else W_DECLINE.pick(rng),
                 IsApproved=approved, EntryMode=W_ENTRY.pick(rng), AuthKind=kind, DebitTransactionId=debit_id)

    pos_by_account: dict[int, list] = {}
    for p in pos_debits:
        pos_by_account.setdefault(p[0], []).append(p)
    for ai, ap in enumerate(st.accounts):
        cards = ainfo[ai]["cards"]
        plist = pos_by_account.get(ai, [])
        for _, did, when, amt, merchant in plist:
            auth(cards[rng.randrange(len(cards))][0], merchant, when - dt.timedelta(minutes=rng.randint(0, 120)),
                 amt, "FINAL", did, True)
        month_pos: dict[int, list] = {}
        for p in plist:
            month_pos.setdefault(p[2].month * 100 + p[2].year % 100, []).append(p)
        extras_total = {}
        for e in ap.extras:
            for k, v in e.items():
                extras_total[k] = extras_total.get(k, 0) + v
        for kind, cnt in extras_total.items():
            for _ in range(cnt):
                _, _, when, amt, merchant = plist[rng.randrange(len(plist))]
                shift = dt.timedelta(minutes=rng.randint(-600, 600))
                if kind == "DECLINED":
                    auth(cards[rng.randrange(len(cards))][0], merchant, when + shift, amt, "FINAL", 0, False)
                else:
                    auth(cards[rng.randrange(len(cards))][0], merchant, when + shift,
                         cents(_lognormal(rng, 35, 0.9, 1, 2500)), kind, 0, True)

    # ------------------------------------------------------------------ loans and payments
    for li, lp in enumerate(st.loans):
        L = loan_info[li]
        lid = nid("Loan")
        orig = _add_months(L["last_due"], -lp.n_payments, 10)
        balance = L["principal"]
        r = L["rate"] / 1200
        c = cinfo[lp.borrower]
        rows_payments = []
        window_idx = {len(lp.window_months) - 1 - i: mo for i, mo in enumerate(reversed(lp.window_months))}
        first_window_k = lp.n_payments - len(lp.window_months)
        for k in range(lp.n_payments):
            due = _add_months(orig, k + 1)
            interest = round(balance * r, 2)
            principal_part = max(0.0, round(L["payment"] - interest, 2))
            balance = max(0.0, round(balance - principal_part, 2))
            debit_id, paid = 0, due + dt.timedelta(days=rng.randint(-5, 20))
            if k >= first_window_k:
                mo = window_idx[k - first_window_k]
                debit_id, when = L["debits"][mo]
                paid = when.date()
            late = paid > due + dt.timedelta(days=10)
            rows_payments.append((due, paid, interest, principal_part, late, debit_id))
        status = W_LOAN_STATUS.pick(rng)
        rows.add("Loan", lid, dt.datetime.combine(orig, dt.time(10, 0), TZ), LoanNumber=f"L{bijective_number(lid, 13, 4242):013d}",
                 CustomerId=c["id"], DisbursementAccountId=ainfo[lp.account]["id"],
                 LoanOfficerEmployeeId=rng.randint(1, emp_max), LoanKind=L["kind"], PrincipalAmount=L["principal"],
                 InterestRate=L["rate"], TermMonths=L["term"], OriginationDate=orig,
                 MaturityDate=_add_months(orig, L["term"]), MonthlyPaymentAmount=L["payment"],
                 OutstandingPrincipal=balance if status != "PAIDOFF" else 0.0,
                 NextPaymentDate=_add_months(ctx.as_of, 1) if status in ("CURRENT", "LATE") else None,
                 LoanStatus=status, CollateralDescription=sized_text(fk, rng, 200, 400),
                 UnderwritingNotes=sized_text(fk, rng, 150, 300))
        for due, paid, interest, principal_part, late, debit_id in rows_payments:
            rows.add("LoanPayment", nid("LoanPayment"), dt.datetime.combine(paid, dt.time(9, 0), TZ), LoanId=lid,
                     DueDate=due, PaymentDate=paid, AmountPaid=L["payment"], PrincipalPortion=principal_part,
                     InterestPortion=interest, LateFee=round(rng.uniform(15, 40), 2) if late else 0.0,
                     DebitTransactionId=debit_id)

    # ------------------------------------------------------------------ logins and audit log
    for ci, cp in enumerate(st.customers):
        cid = cinfo[ci]["id"]
        device = fk.hexify("^" * 32)
        for _ in range(cp.n_logins):
            when = rand_datetime(rng, rand_day(rng, win_start, ctx.as_of))
            kind = W_LOGIN.pick(rng)
            rows.add("LoginEvent", nid("LoginEvent"), when, CustomerId=cid, EventDateTime=when, EventKind=kind,
                     Channel=rng.choice(["WEB", "MOBILE"]), IpAddress=fk.ipv4() if rng.random() < 0.9 else fk.ipv6(),
                     DeviceId=device if rng.random() < 0.8 else fk.hexify("^" * 32), IsSuccess=kind != "FAILED",
                     SessionSeconds=rng.randint(30, 3600) if kind in ("LOGIN", "LOGOUT") else 0)
    targets = {"Customer": cust_ids, "Account": acct_ids,
               "Card": [cid for a in ainfo for cid, _ in a["cards"]]}
    audit = []
    for cp in st.customers:
        for _ in range(cp.n_audit):
            table = W_AUDIT_TABLE.pick(rng)
            if not targets[table]:
                table = "Customer"
            audit.append((rand_datetime(rng, rand_day(rng, win_start, ctx.as_of), False), table,
                          rng.choice(targets[table])))
    audit.sort(key=lambda x: x[0])
    for when, table, record in audit:
        action = W_AUDIT_ACTION.pick(rng)
        rows.add("AuditLog", nid("AuditLog"), when, EventDateTime=when, TableName=table, RecordId=record,
                 AuditAction=action, EmployeeId=0 if rng.random() < 0.7 else rng.randint(1, emp_max),
                 ChangeSummary={"C": f"{table} created", "D": f"{table} deleted"}.get(action,
                               f"{rng.choice(['Status', 'Email', 'Limit', 'Nickname', 'Address'])} updated")[:60])

    got = rows.counts()
    if got != planned:
        diff = {t: (planned.get(t), got.get(t)) for t in set(planned) | set(got) if planned.get(t) != got.get(t)}
        raise AssertionError(f"unit {unit['UnitNo']}: generated counts differ from plan: {diff}")
    return rows.tables
