# MonthlyBalance

`Class T (Transactional)` · `Large` · `Standard` · `LOB: none`

[← Schema overview](../README.md)

## Description

Month-end balance snapshot per account (opening/closing/min/max/average balance, totals).

## Facts

| Property | Value |
|---|---|
| Rows at scale factor 1 | 18,000,000 |
| Scaling | linear (rows × scale factor) |
| Volume tier | Large |
| Estimated average record | 160 bytes (field-by-field estimate: 122 bytes) |
| Record-size tier | Standard |
| Estimated data at SF 1 | 2.880 GB |
| Data area | `PB_Txn_Large` (RPB 32, BPC 512) |
| Index area | `PB_Txn_Idx` (BPC 512) |
| Sequence | `SeqMonthlyBalanceId` (INT64, starts at 1, increment 1, no cycle) |

## Fields

17 fields. *(std)* marks the standard fields present on every table.

| # | Name | Type | Format | Decimals | Mandatory | Initial | Label | Description | Generation |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `MonthlyBalanceId` *(std)* | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Monthly Balance Id | Dense sequential identifier, 1..N with no gaps after the initial load. Runtime inserts use NEXT-VALUE(SeqMonthlyBalanceId). | Assigned 1..N in load order |
| 2 | `RandomInt10` *(std)* | INTEGER | `>9` |  | Y | `0` | Random Int 10 | Independent uniform random value 1–10 for selecting ≈ 10% subsets. 0 = unassigned (invalid). | Independent uniform 1–10; 0 = unassigned (invalid) |
| 3 | `RandomInt100` *(std)* | INTEGER | `>>9` |  | Y | `0` | Random Int 100 | Independent uniform random value 1–100 for selecting ≈ 1% subsets. 0 = unassigned (invalid). | Independent uniform 1–100; 0 = unassigned (invalid) |
| 4 | `RandomInt1000` *(std)* | INTEGER | `>>>9` |  | Y | `0` | Random Int 1000 | Independent uniform random value 1–1000 for selecting ≈ 0.1% subsets. 0 = unassigned (invalid). | Independent uniform 1–1000; 0 = unassigned (invalid) |
| 5 | `CreatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Created At | When the row was created. For historical rows, a synthetic timestamp consistent with the row's business date. | Consistent with the row's business date; NOW for runtime inserts |
| 6 | `AccountId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Account Id | Reference to [Account](Account.md).`AccountId` | Random existing parent row, respecting the cardinality |
| 7 | `BalanceMonth` | DATE | `99/99/9999` |  | Y | `?` (unknown) | Balance Month | Month the snapshot describes | First day of the month |
| 8 | `OpeningBalance` | DECIMAL | `->>>,>>>,>>>,>>9.99` | 2 | Y | `0` | Opening Balance | Balance at period start | default (data-model §1.5) |
| 9 | `ClosingBalance` | DECIMAL | `->>>,>>>,>>>,>>9.99` | 2 | Y | `0` | Closing Balance | Balance at period end | default (data-model §1.5) |
| 10 | `MinimumBalance` | DECIMAL | `->>>,>>>,>>>,>>9.99` | 2 | Y | `0` | Minimum Balance | Minimum balance | default (data-model §1.5) |
| 11 | `MaximumBalance` | DECIMAL | `->>>,>>>,>>>,>>9.99` | 2 | Y | `0` | Maximum Balance | Highest balance during the period | default (data-model §1.5) |
| 12 | `AverageDailyBalance` | DECIMAL | `->>>,>>>,>>>,>>9.99` | 2 | Y | `0` | Average Daily Balance | Average of end-of-day balances | default (data-model §1.5) |
| 13 | `TotalDebits` | DECIMAL | `->>>,>>>,>>>,>>9.99` | 2 | Y | `0` | Total Debits | Sum of debit amounts in the period | default (data-model §1.5) |
| 14 | `TotalCredits` | DECIMAL | `->>>,>>>,>>>,>>9.99` | 2 | Y | `0` | Total Credits | Sum of credit amounts in the period | default (data-model §1.5) |
| 15 | `DebitCount` | INTEGER | `>>>>9` |  | Y | `0` | Debit Count | Number of debits in the period | default (data-model §1.5) |
| 16 | `CreditCount` | INTEGER | `>>>>9` |  | Y | `0` | Credit Count | Number of credits in the period | default (data-model §1.5) |
| 17 | `DaysOverdrawn` | INTEGER | `>9` |  | Y | `0` | Days Overdrawn | Days with a negative end-of-day balance | 0–31; 97% are 0 |

## Indexes

6 indexes (2 table-specific).

| Name | Components | Primary | Unique | Word | Purpose |
|---|---|---|---|---|---|
| `PkMonthlyBalance` *(std)* | MonthlyBalanceId ASC | Y | Y | N | Single-row random access by sequential ID; default scan order |
| `IxRandomInt10` *(std)* | RandomInt10 ASC, MonthlyBalanceId ASC | N | N | N | Select ≈ 10% of rows (RandomInt10 = k) |
| `IxRandomInt100` *(std)* | RandomInt100 ASC, MonthlyBalanceId ASC | N | N | N | Select ≈ 1% of rows (RandomInt100 = k) |
| `IxRandomInt1000` *(std)* | RandomInt1000 ASC, MonthlyBalanceId ASC | N | N | N | Select ≈ 0.1% of rows (RandomInt1000 = k) |
| `UxAccountMonth` | AccountId ASC, BalanceMonth ASC | N | Y | N | An account's history |
| `IxBalanceMonth` | BalanceMonth ASC | N | N | N | Month-wide aggregates |

## Relationships

**Parents**

- `AccountId` → [Account](Account.md).`AccountId` — 12 / 1–12 children per parent

**Children**

- none

## Access examples

ABL: about 1% of rows, then one random existing row.

```abl
FOR EACH MonthlyBalance NO-LOCK WHERE MonthlyBalance.RandomInt100 = 42 USE-INDEX IxRandomInt100:
    /* work */
END.

DEFINE VARIABLE r AS INT64 NO-UNDO.
FIND BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.TableName = "MonthlyBalance".
r = RANDOM(1, INTEGER(BenchmarkTableInfo.MaxId)).
FIND MonthlyBalance NO-LOCK WHERE MonthlyBalance.MonthlyBalanceId = r NO-ERROR.   /* not AVAILABLE => draw again */
```

SQL:

```sql
SELECT * FROM PUB.MonthlyBalance WHERE RandomInt100 = 42;
SELECT MaxId FROM PUB.BenchmarkTableInfo WHERE TableName = 'MonthlyBalance';
SELECT * FROM PUB.MonthlyBalance WHERE MonthlyBalanceId = ?;   -- ? drawn uniformly from 1..MaxId
```
