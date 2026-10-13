# CreditTransaction

`Class T (Transactional)` · `Large` · `Standard` · `LOB: none`

[← Schema overview](../README.md)

## Description

Money entering an account.

## Facts

| Property | Value |
|---|---|
| Rows at scale factor 1 | 18,000,000 |
| Scaling | linear (rows × scale factor) |
| Volume tier | Large |
| Estimated average record | 170 bytes (field-by-field estimate: 165 bytes) |
| Record-size tier | Standard |
| Estimated data at SF 1 | 3.060 GB |
| Data area | `PB_Txn_Large` (RPB 32, BPC 512) |
| Index area | `PB_Txn_Idx` (BPC 512) |
| Sequence | `SeqCreditTransactionId` (INT64, starts at 1, increment 1, no cycle) |

## Fields

16 fields. *(std)* marks the standard fields present on every table.

| # | Name | Type | Format | Decimals | Mandatory | Initial | Label | Description | Generation |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `CreditTransactionId` *(std)* | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Credit Transaction Id | Dense sequential identifier, 1..N with no gaps after the initial load. Runtime inserts use NEXT-VALUE(SeqCreditTransactionId). | Assigned 1..N in load order |
| 2 | `RandomInt10` *(std)* | INTEGER | `>9` |  | Y | `0` | Random Int 10 | Independent uniform random value 1–10 for selecting ≈ 10% subsets. 0 = unassigned (invalid). | Independent uniform 1–10; 0 = unassigned (invalid) |
| 3 | `RandomInt100` *(std)* | INTEGER | `>>9` |  | Y | `0` | Random Int 100 | Independent uniform random value 1–100 for selecting ≈ 1% subsets. 0 = unassigned (invalid). | Independent uniform 1–100; 0 = unassigned (invalid) |
| 4 | `RandomInt1000` *(std)* | INTEGER | `>>>9` |  | Y | `0` | Random Int 1000 | Independent uniform random value 1–1000 for selecting ≈ 0.1% subsets. 0 = unassigned (invalid). | Independent uniform 1–1000; 0 = unassigned (invalid) |
| 5 | `CreatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Created At | When the row was created. For historical rows, a synthetic timestamp consistent with the row's business date. | Consistent with the row's business date; NOW for runtime inserts |
| 6 | `AccountId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Account Id | Reference to [Account](Account.md).`AccountId` | Random existing parent row, respecting the cardinality |
| 7 | `TransactionTypeId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Transaction Type Id | Reference to [TransactionType](TransactionType.md).`TransactionTypeId` | Random existing parent row, respecting the cardinality |
| 8 | `AccountStatementId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Account Statement Id | Reference to [AccountStatement](AccountStatement.md).`AccountStatementId` | 0 = not yet on a statement (runtime inserts) |
| 9 | `PostedDate` | DATE | `99/99/9999` |  | Y | `?` (unknown) | Posted Date | Business date the transaction posted | default (data-model §1.5) |
| 10 | `PostedAt` | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `?` (unknown) | Posted At | Timestamp the transaction posted | default (data-model §1.5) |
| 11 | `Amount` | DECIMAL | `->>>,>>>,>>>,>>9.99` | 2 | Y | `0` | Amount | Amount credited (positive) | > 0; payroll 1,000–8,000; other log-normal |
| 12 | `RunningBalance` | DECIMAL | `->>>,>>>,>>>,>>9.99` | 2 | Y | `0` | Running Balance | Account balance after posting | Account balance after posting |
| 13 | `Description` | CHARACTER | `x(60)` |  | Y | `""` | Description | Human-readable description | default (data-model §1.5) |
| 14 | `PayerName` | CHARACTER | `x(60)` |  | Y | `""` | Payer Name | Name of the payer | default (data-model §1.5) |
| 15 | `ReferenceNumber` | CHARACTER | `x(20)` |  | Y | `""` | Reference Number | External reference number | default (data-model §1.5) |
| 16 | `IsPayroll` | LOGICAL | `yes/no` |  | Y | `no` | Is Payroll | 40% yes | 40% yes |

## Indexes

7 indexes (3 table-specific).

| Name | Components | Primary | Unique | Word | Purpose |
|---|---|---|---|---|---|
| `PkCreditTransaction` *(std)* | CreditTransactionId ASC | Y | Y | N | Single-row random access by sequential ID; default scan order |
| `IxRandomInt10` *(std)* | RandomInt10 ASC, CreditTransactionId ASC | N | N | N | Select ≈ 10% of rows (RandomInt10 = k) |
| `IxRandomInt100` *(std)* | RandomInt100 ASC, CreditTransactionId ASC | N | N | N | Select ≈ 1% of rows (RandomInt100 = k) |
| `IxRandomInt1000` *(std)* | RandomInt1000 ASC, CreditTransactionId ASC | N | N | N | Select ≈ 0.1% of rows (RandomInt1000 = k) |
| `IxAccountPosted` | AccountId ASC, PostedAt DESC | N | N | N | Transaction history, newest first |
| `IxAccountStatement` | AccountStatementId ASC | N | N | N | Statement detail (all transactions on one statement) |
| `IxPostedDate` | PostedDate ASC | N | N | N | Daily batch/range scans |

## Relationships

**Parents**

- `AccountId` → [Account](Account.md).`AccountId` — 12 / 0–100 children per parent
- `TransactionTypeId` → [TransactionType](TransactionType.md).`TransactionTypeId` — 750,000 / 0–7,000,000 children per parent; not indexed: Same as above
- `AccountStatementId` → [AccountStatement](AccountStatement.md).`AccountStatementId` — 1 / 0–15 children per parent; optional (0 = none)

**Children**

- [Transfer](Transfer.md).`CreditTransactionId`

## Access examples

ABL: about 1% of rows, then one random existing row.

```abl
FOR EACH CreditTransaction NO-LOCK WHERE CreditTransaction.RandomInt100 = 42 USE-INDEX IxRandomInt100:
    /* work */
END.

DEFINE VARIABLE r AS INT64 NO-UNDO.
FIND BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.TableName = "CreditTransaction".
r = RANDOM(1, INTEGER(BenchmarkTableInfo.MaxId)).
FIND CreditTransaction NO-LOCK WHERE CreditTransaction.CreditTransactionId = r NO-ERROR.   /* not AVAILABLE => draw again */
```

SQL:

```sql
SELECT * FROM PUB.CreditTransaction WHERE RandomInt100 = 42;
SELECT MaxId FROM PUB.BenchmarkTableInfo WHERE TableName = 'CreditTransaction';
SELECT * FROM PUB.CreditTransaction WHERE CreditTransactionId = ?;   -- ? drawn uniformly from 1..MaxId
```
