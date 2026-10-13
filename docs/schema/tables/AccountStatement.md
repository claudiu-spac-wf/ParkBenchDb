# AccountStatement

`Class T (Transactional)` · `Large` · `LOB-bearing` · `LOB: CLOB`

[← Schema overview](../README.md)

## Description

Periodic account statement summary.

## Facts

| Property | Value |
|---|---|
| Rows at scale factor 1 | 18,000,000 |
| Scaling | linear (rows × scale factor) |
| Volume tier | Large |
| Estimated average record | 190 bytes (field-by-field estimate: 139 bytes) |
| Record-size tier | LOB-bearing |
| Estimated data at SF 1 | 3.420 GB |
| Estimated LOB content at SF 1 | 0.276 GB |
| Data area | `PB_Txn_Large` (RPB 32, BPC 512) |
| Index area | `PB_Txn_Idx` (BPC 512) |
| LOB areas | `PB_Lob_Text` (BPC 512) |
| Sequence | `SeqAccountStatementId` (INT64, starts at 1, increment 1, no cycle) |

## Fields

19 fields. *(std)* marks the standard fields present on every table.

| # | Name | Type | Format | Decimals | Mandatory | Initial | Label | Description | Generation |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `AccountStatementId` *(std)* | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Account Statement Id | Dense sequential identifier, 1..N with no gaps after the initial load. Runtime inserts use NEXT-VALUE(SeqAccountStatementId). | Assigned 1..N in load order |
| 2 | `RandomInt10` *(std)* | INTEGER | `>9` |  | Y | `0` | Random Int 10 | Independent uniform random value 1–10 for selecting ≈ 10% subsets. 0 = unassigned (invalid). | Independent uniform 1–10; 0 = unassigned (invalid) |
| 3 | `RandomInt100` *(std)* | INTEGER | `>>9` |  | Y | `0` | Random Int 100 | Independent uniform random value 1–100 for selecting ≈ 1% subsets. 0 = unassigned (invalid). | Independent uniform 1–100; 0 = unassigned (invalid) |
| 4 | `RandomInt1000` *(std)* | INTEGER | `>>>9` |  | Y | `0` | Random Int 1000 | Independent uniform random value 1–1000 for selecting ≈ 0.1% subsets. 0 = unassigned (invalid). | Independent uniform 1–1000; 0 = unassigned (invalid) |
| 5 | `CreatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Created At | When the row was created. For historical rows, a synthetic timestamp consistent with the row's business date. | Consistent with the row's business date; NOW for runtime inserts |
| 6 | `AccountId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Account Id | Reference to [Account](Account.md).`AccountId` | Random existing parent row, respecting the cardinality |
| 7 | `PeriodStart` | DATE | `99/99/9999` |  | Y | `?` (unknown) | Period Start | First day of the statement period | First of the month |
| 8 | `PeriodEnd` | DATE | `99/99/9999` |  | Y | `?` (unknown) | Period End | Last day of the statement period | Last of the month |
| 9 | `OpeningBalance` | DECIMAL | `->>>,>>>,>>>,>>9.99` | 2 | Y | `0` | Opening Balance | Balance at period start | Equals the previous statement's ClosingBalance |
| 10 | `ClosingBalance` | DECIMAL | `->>>,>>>,>>>,>>9.99` | 2 | Y | `0` | Closing Balance | Balance at period end | Opening − debits + credits |
| 11 | `TotalDebits` | DECIMAL | `->>>,>>>,>>>,>>9.99` | 2 | Y | `0` | Total Debits | Sum of debit amounts in the period | Sum of the linked DebitTransaction.Amount |
| 12 | `TotalCredits` | DECIMAL | `->>>,>>>,>>>,>>9.99` | 2 | Y | `0` | Total Credits | Sum of credit amounts in the period | Sum of the linked CreditTransaction.Amount |
| 13 | `DebitCount` | INTEGER | `>>>>9` |  | Y | `0` | Debit Count | Number of debits in the period | default (data-model §1.5) |
| 14 | `CreditCount` | INTEGER | `>>>>9` |  | Y | `0` | Credit Count | Number of credits in the period | default (data-model §1.5) |
| 15 | `InterestEarned` | DECIMAL | `->>>,>>>,>>>,>>9.99` | 2 | Y | `0` | Interest Earned | Interest credited in the period | default (data-model §1.5) |
| 16 | `FeesCharged` | DECIMAL | `->>>,>>>,>>>,>>9.99` | 2 | Y | `0` | Fees Charged | Fees charged in the period | default (data-model §1.5) |
| 17 | `DeliveryMethod` | CHARACTER | `x(6)` |  | Y | `PAPER` | Delivery Method | How the statement is delivered | EMAIL for paperless customers |
| 18 | `GeneratedAt` | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `?` (unknown) | Generated At | When the statement was generated | PeriodEnd + 1 day, 02:00–05:00 |
| 19 | `NoticeText` | CLOB | – |  | N | `?` (unknown) | Notice Text | Regulatory/marketing notice; present on 1%; 0.5–4 KB (avg 1.5 KB). Area PB_Lob_Text | Regulatory/marketing notice; present on 1%; 0.5–4 KB (avg 1.5 KB). Area PB_Lob_Text |

## LOB fields

| Field | Type | Area | Max size | Codepage | Content | Populated | Min / Avg / Max bytes |
|---|---|---|---|---|---|---|---|
| `NoticeText` | CLOB | `PB_Lob_Text` | 4K | UTF-8 | regulatory/marketing notice text | 1% | 512 / 1,536 / 4,096 |

## Indexes

6 indexes (2 table-specific).

| Name | Components | Primary | Unique | Word | Purpose |
|---|---|---|---|---|---|
| `PkAccountStatement` *(std)* | AccountStatementId ASC | Y | Y | N | Single-row random access by sequential ID; default scan order |
| `IxRandomInt10` *(std)* | RandomInt10 ASC, AccountStatementId ASC | N | N | N | Select ≈ 10% of rows (RandomInt10 = k) |
| `IxRandomInt100` *(std)* | RandomInt100 ASC, AccountStatementId ASC | N | N | N | Select ≈ 1% of rows (RandomInt100 = k) |
| `IxRandomInt1000` *(std)* | RandomInt1000 ASC, AccountStatementId ASC | N | N | N | Select ≈ 0.1% of rows (RandomInt1000 = k) |
| `UxAccountPeriod` | AccountId ASC, PeriodEnd DESC | N | Y | N | An account's statements, newest first |
| `IxPeriodEnd` | PeriodEnd ASC | N | N | N | Month-end batch |

## Relationships

**Parents**

- `AccountId` → [Account](Account.md).`AccountId` — 12 / 1–12 children per parent

**Children**

- [StatementDocument](StatementDocument.md).`AccountStatementId`
- [CreditTransaction](CreditTransaction.md).`AccountStatementId`
- [DebitTransaction](DebitTransaction.md).`AccountStatementId`

## Access examples

ABL: about 1% of rows, then one random existing row.

```abl
FOR EACH AccountStatement NO-LOCK WHERE AccountStatement.RandomInt100 = 42 USE-INDEX IxRandomInt100:
    /* work */
END.

DEFINE VARIABLE r AS INT64 NO-UNDO.
FIND BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.TableName = "AccountStatement".
r = RANDOM(1, INTEGER(BenchmarkTableInfo.MaxId)).
FIND AccountStatement NO-LOCK WHERE AccountStatement.AccountStatementId = r NO-ERROR.   /* not AVAILABLE => draw again */
```

SQL:

```sql
SELECT * FROM PUB.AccountStatement WHERE RandomInt100 = 42;
SELECT MaxId FROM PUB.BenchmarkTableInfo WHERE TableName = 'AccountStatement';
SELECT * FROM PUB.AccountStatement WHERE AccountStatementId = ?;   -- ? drawn uniformly from 1..MaxId
```
