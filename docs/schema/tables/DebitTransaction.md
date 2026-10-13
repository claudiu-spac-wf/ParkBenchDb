# DebitTransaction

`Class T (Transactional)` · `Very Large` · `Standard` · `LOB: none`

[← Schema overview](../README.md)

## Description

Money leaving an account.

## Facts

| Property | Value |
|---|---|
| Rows at scale factor 1 | 50,000,000 |
| Scaling | linear (rows × scale factor) |
| Volume tier | Very Large |
| Estimated average record | 170 bytes (field-by-field estimate: 141 bytes) |
| Record-size tier | Standard |
| Estimated data at SF 1 | 8.500 GB |
| Data area | `PB_Txn_Debit` (RPB 32, BPC 512) |
| Index area | `PB_Txn_Idx` (BPC 512) |
| Sequence | `SeqDebitTransactionId` (INT64, starts at 1, increment 1, no cycle) |

## Fields

16 fields. *(std)* marks the standard fields present on every table.

| # | Name | Type | Format | Decimals | Mandatory | Initial | Label | Description | Generation |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `DebitTransactionId` *(std)* | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Debit Transaction Id | Dense sequential identifier, 1..N with no gaps after the initial load. Runtime inserts use NEXT-VALUE(SeqDebitTransactionId). | Assigned 1..N in load order |
| 2 | `RandomInt10` *(std)* | INTEGER | `>9` |  | Y | `0` | Random Int 10 | Independent uniform random value 1–10 for selecting ≈ 10% subsets. 0 = unassigned (invalid). | Independent uniform 1–10; 0 = unassigned (invalid) |
| 3 | `RandomInt100` *(std)* | INTEGER | `>>9` |  | Y | `0` | Random Int 100 | Independent uniform random value 1–100 for selecting ≈ 1% subsets. 0 = unassigned (invalid). | Independent uniform 1–100; 0 = unassigned (invalid) |
| 4 | `RandomInt1000` *(std)* | INTEGER | `>>>9` |  | Y | `0` | Random Int 1000 | Independent uniform random value 1–1000 for selecting ≈ 0.1% subsets. 0 = unassigned (invalid). | Independent uniform 1–1000; 0 = unassigned (invalid) |
| 5 | `CreatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Created At | When the row was created. For historical rows, a synthetic timestamp consistent with the row's business date. | Consistent with the row's business date; NOW for runtime inserts |
| 6 | `AccountId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Account Id | Reference to [Account](Account.md).`AccountId` | skewed (active checking accounts dominate) |
| 7 | `TransactionTypeId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Transaction Type Id | Reference to [TransactionType](TransactionType.md).`TransactionTypeId` | POS 50%, ACH 12%, ATM 8%, XFER 12% (= Transfer rows), LOANPMT 6% (= LoanPayment rows in window), FEE 4%, other 8% |
| 8 | `AccountStatementId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Account Statement Id | Reference to [AccountStatement](AccountStatement.md).`AccountStatementId` | 0 = not yet on a statement |
| 9 | `MerchantId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Merchant Id | Reference to [Merchant](Merchant.md).`MerchantId` | set for POS/ecommerce, otherwise 0 |
| 10 | `PostedDate` | DATE | `99/99/9999` |  | Y | `?` (unknown) | Posted Date | Business date the transaction posted | default (data-model §1.5) |
| 11 | `PostedAt` | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `?` (unknown) | Posted At | Timestamp the transaction posted | Diurnal distribution |
| 12 | `Amount` | DECIMAL | `->>>,>>>,>>>,>>9.99` | 2 | Y | `0` | Amount | Amount debited (positive) | > 0; log-normal (median ≈ 35) |
| 13 | `RunningBalance` | DECIMAL | `->>>,>>>,>>>,>>9.99` | 2 | Y | `0` | Running Balance | Balance after posting; may be negative | Balance after posting; may be negative |
| 14 | `Description` | CHARACTER | `x(60)` |  | Y | `""` | Description | Human-readable description | Merchant name or type description |
| 15 | `ReferenceNumber` | CHARACTER | `x(20)` |  | Y | `""` | Reference Number | External reference number | default (data-model §1.5) |
| 16 | `CheckNumber` | INTEGER | `>>>>>9` |  | Y | `0` | Check Number | Set on 1% of rows (checks) | Set on 1% of rows (checks) |

## Indexes

8 indexes (4 table-specific).

| Name | Components | Primary | Unique | Word | Purpose |
|---|---|---|---|---|---|
| `PkDebitTransaction` *(std)* | DebitTransactionId ASC | Y | Y | N | Single-row random access by sequential ID; default scan order |
| `IxRandomInt10` *(std)* | RandomInt10 ASC, DebitTransactionId ASC | N | N | N | Select ≈ 10% of rows (RandomInt10 = k) |
| `IxRandomInt100` *(std)* | RandomInt100 ASC, DebitTransactionId ASC | N | N | N | Select ≈ 1% of rows (RandomInt100 = k) |
| `IxRandomInt1000` *(std)* | RandomInt1000 ASC, DebitTransactionId ASC | N | N | N | Select ≈ 0.1% of rows (RandomInt1000 = k) |
| `IxAccountPosted` | AccountId ASC, PostedAt DESC | N | N | N | Transaction history, newest first |
| `IxAccountStatement` | AccountStatementId ASC | N | N | N | Statement detail (all transactions on one statement) |
| `IxPostedDate` | PostedDate ASC | N | N | N | Daily batch/range scans |
| `IxMerchantDate` | MerchantId ASC, PostedDate ASC | N | N | N | Merchant analytics |

## Relationships

**Parents**

- `AccountId` → [Account](Account.md).`AccountId` — 33 / 0–400 (skewed) children per parent
- `TransactionTypeId` → [TransactionType](TransactionType.md).`TransactionTypeId` — 2,500,000 / 0–25,000,000 (POS 50%) children per parent; not indexed: Tiny parent; an index would have 60 distinct keys over 50M rows
- `AccountStatementId` → [AccountStatement](AccountStatement.md).`AccountStatementId` — 2.8 / 0–40 children per parent; optional (0 = none)
- `MerchantId` → [Merchant](Merchant.md).`MerchantId` — 375 / 0–50,000 (Zipf; ≈ 60% of rows set) children per parent; optional (0 = none)

**Children**

- [Transfer](Transfer.md).`DebitTransactionId`
- [LoanPayment](LoanPayment.md).`DebitTransactionId`
- [CardAuthorization](CardAuthorization.md).`DebitTransactionId`

## Access examples

ABL: about 1% of rows, then one random existing row.

```abl
FOR EACH DebitTransaction NO-LOCK WHERE DebitTransaction.RandomInt100 = 42 USE-INDEX IxRandomInt100:
    /* work */
END.

DEFINE VARIABLE r AS INT64 NO-UNDO.
FIND BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.TableName = "DebitTransaction".
r = RANDOM(1, INTEGER(BenchmarkTableInfo.MaxId)).
FIND DebitTransaction NO-LOCK WHERE DebitTransaction.DebitTransactionId = r NO-ERROR.   /* not AVAILABLE => draw again */
```

SQL:

```sql
SELECT * FROM PUB.DebitTransaction WHERE RandomInt100 = 42;
SELECT MaxId FROM PUB.BenchmarkTableInfo WHERE TableName = 'DebitTransaction';
SELECT * FROM PUB.DebitTransaction WHERE DebitTransactionId = ?;   -- ? drawn uniformly from 1..MaxId
```
