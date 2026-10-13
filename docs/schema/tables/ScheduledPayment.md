# ScheduledPayment

`Class M (Master)` · `Medium` · `Standard` · `LOB: none`

[← Schema overview](../README.md)

## Description

Recurring/future-dated payments.

## Facts

| Property | Value |
|---|---|
| Rows at scale factor 1 | 1,000,000 |
| Scaling | linear (rows × scale factor) |
| Volume tier | Medium |
| Estimated average record | 180 bytes (field-by-field estimate: 135 bytes) |
| Record-size tier | Standard |
| Estimated data at SF 1 | 0.180 GB |
| Data area | `PB_Master_Std` (RPB 16, BPC 64) |
| Index area | `PB_Master_Idx` (BPC 64) |
| Sequence | `SeqScheduledPaymentId` (INT64, starts at 1, increment 1, no cycle) |

## Fields

16 fields. *(std)* marks the standard fields present on every table.

| # | Name | Type | Format | Decimals | Mandatory | Initial | Label | Description | Generation |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `ScheduledPaymentId` *(std)* | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Scheduled Payment Id | Dense sequential identifier, 1..N with no gaps after the initial load. Runtime inserts use NEXT-VALUE(SeqScheduledPaymentId). | Assigned 1..N in load order |
| 2 | `RandomInt10` *(std)* | INTEGER | `>9` |  | Y | `0` | Random Int 10 | Independent uniform random value 1–10 for selecting ≈ 10% subsets. 0 = unassigned (invalid). | Independent uniform 1–10; 0 = unassigned (invalid) |
| 3 | `RandomInt100` *(std)* | INTEGER | `>>9` |  | Y | `0` | Random Int 100 | Independent uniform random value 1–100 for selecting ≈ 1% subsets. 0 = unassigned (invalid). | Independent uniform 1–100; 0 = unassigned (invalid) |
| 4 | `RandomInt1000` *(std)* | INTEGER | `>>>9` |  | Y | `0` | Random Int 1000 | Independent uniform random value 1–1000 for selecting ≈ 0.1% subsets. 0 = unassigned (invalid). | Independent uniform 1–1000; 0 = unassigned (invalid) |
| 5 | `CreatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Created At | When the row was created. For historical rows, a synthetic timestamp consistent with the row's business date. | Consistent with the row's business date; NOW for runtime inserts |
| 6 | `AccountId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Account Id | Reference to [Account](Account.md).`AccountId` | Random existing parent row, respecting the cardinality |
| 7 | `PayeeId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Payee Id | Reference to [Payee](Payee.md).`PayeeId` | Random existing parent row, respecting the cardinality |
| 8 | `Amount` | DECIMAL | `->>>,>>>,>>>,>>9.99` | 2 | Y | `0` | Amount | Amount paid on each run | 10–5,000 |
| 9 | `Frequency` | CHARACTER | `x(10)` |  | Y | `MONTHLY` | Frequency | Recurrence frequency | ONCE, WEEKLY, BIWEEKLY, MONTHLY, QUARTERLY |
| 10 | `NextRunDate` | DATE | `99/99/9999` |  | N | `?` (unknown) | Next Run Date | Date of the next execution | Unknown when not ACTIVE |
| 11 | `EndDate` | DATE | `99/99/9999` |  | N | `?` (unknown) | End Date | Last date the schedule runs | default (data-model §1.5) |
| 12 | `Memo` | CHARACTER | `x(60)` |  | Y | `""` | Memo | Payment memo | default (data-model §1.5) |
| 13 | `PaymentStatus` | CHARACTER | `x(10)` |  | Y | `ACTIVE` | Payment Status | Lifecycle status | ACTIVE 70%, PAUSED 5%, CANCELLED 15%, COMPLETED 10% |
| 14 | `RunCount` | INTEGER | `>>>9` |  | Y | `0` | Run Count | Number of executions so far | default (data-model §1.5) |
| 15 | `LastRunAt` | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | N | `?` (unknown) | Last Run At | When the schedule last ran | default (data-model §1.5) |
| 16 | `UpdatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Updated At | Last modification time; equals CreatedAt right after the load. | Equal to CreatedAt at load |

## Indexes

7 indexes (3 table-specific).

| Name | Components | Primary | Unique | Word | Purpose |
|---|---|---|---|---|---|
| `PkScheduledPayment` *(std)* | ScheduledPaymentId ASC | Y | Y | N | Single-row random access by sequential ID; default scan order |
| `IxRandomInt10` *(std)* | RandomInt10 ASC, ScheduledPaymentId ASC | N | N | N | Select ≈ 10% of rows (RandomInt10 = k) |
| `IxRandomInt100` *(std)* | RandomInt100 ASC, ScheduledPaymentId ASC | N | N | N | Select ≈ 1% of rows (RandomInt100 = k) |
| `IxRandomInt1000` *(std)* | RandomInt1000 ASC, ScheduledPaymentId ASC | N | N | N | Select ≈ 0.1% of rows (RandomInt1000 = k) |
| `IxAccount` | AccountId ASC | N | N | N | An account's schedules |
| `IxPayee` | PayeeId ASC | N | N | N | Payments to a payee |
| `IxStatusNextRun` | PaymentStatus ASC, NextRunDate ASC | N | N | N | Daily payment-run batch |

## Relationships

**Parents**

- `AccountId` → [Account](Account.md).`AccountId` — 0.67 / 0–10 children per parent
- `PayeeId` → [Payee](Payee.md).`PayeeId` — 0.4 / 0–3 children per parent

**Children**

- none

## Access examples

ABL: about 1% of rows, then one random existing row.

```abl
FOR EACH ScheduledPayment NO-LOCK WHERE ScheduledPayment.RandomInt100 = 42 USE-INDEX IxRandomInt100:
    /* work */
END.

DEFINE VARIABLE r AS INT64 NO-UNDO.
FIND BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.TableName = "ScheduledPayment".
r = RANDOM(1, INTEGER(BenchmarkTableInfo.MaxId)).
FIND ScheduledPayment NO-LOCK WHERE ScheduledPayment.ScheduledPaymentId = r NO-ERROR.   /* not AVAILABLE => draw again */
```

SQL:

```sql
SELECT * FROM PUB.ScheduledPayment WHERE RandomInt100 = 42;
SELECT MaxId FROM PUB.BenchmarkTableInfo WHERE TableName = 'ScheduledPayment';
SELECT * FROM PUB.ScheduledPayment WHERE ScheduledPaymentId = ?;   -- ? drawn uniformly from 1..MaxId
```
