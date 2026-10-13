# Transfer

`Class T (Transactional)` · `Large` · `Narrow` · `LOB: none`

[← Schema overview](../README.md)

## Description

Movement between two accounts, linking one debit and one credit.

Each transfer creates one DebitTransaction on the source account and one CreditTransaction on the destination account, both with transaction type XFER.

## Facts

| Property | Value |
|---|---|
| Rows at scale factor 1 | 6,000,000 |
| Scaling | linear (rows × scale factor) |
| Volume tier | Large |
| Estimated average record | 100 bytes (field-by-field estimate: 94 bytes) |
| Record-size tier | Narrow |
| Estimated data at SF 1 | 0.600 GB |
| Data area | `PB_Txn_Large` (RPB 32, BPC 512) |
| Index area | `PB_Txn_Idx` (BPC 512) |
| Sequence | `SeqTransferId` (INT64, starts at 1, increment 1, no cycle) |

## Fields

13 fields. *(std)* marks the standard fields present on every table.

| # | Name | Type | Format | Decimals | Mandatory | Initial | Label | Description | Generation |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `TransferId` *(std)* | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Transfer Id | Dense sequential identifier, 1..N with no gaps after the initial load. Runtime inserts use NEXT-VALUE(SeqTransferId). | Assigned 1..N in load order |
| 2 | `RandomInt10` *(std)* | INTEGER | `>9` |  | Y | `0` | Random Int 10 | Independent uniform random value 1–10 for selecting ≈ 10% subsets. 0 = unassigned (invalid). | Independent uniform 1–10; 0 = unassigned (invalid) |
| 3 | `RandomInt100` *(std)* | INTEGER | `>>9` |  | Y | `0` | Random Int 100 | Independent uniform random value 1–100 for selecting ≈ 1% subsets. 0 = unassigned (invalid). | Independent uniform 1–100; 0 = unassigned (invalid) |
| 4 | `RandomInt1000` *(std)* | INTEGER | `>>>9` |  | Y | `0` | Random Int 1000 | Independent uniform random value 1–1000 for selecting ≈ 0.1% subsets. 0 = unassigned (invalid). | Independent uniform 1–1000; 0 = unassigned (invalid) |
| 5 | `CreatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Created At | When the row was created. For historical rows, a synthetic timestamp consistent with the row's business date. | Consistent with the row's business date; NOW for runtime inserts |
| 6 | `FromAccountId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | From Account Id | Reference to [Account](Account.md).`AccountId` | Random existing parent row, respecting the cardinality |
| 7 | `ToAccountId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | To Account Id | Reference to [Account](Account.md).`AccountId` | Random existing parent row, respecting the cardinality |
| 8 | `Amount` | DECIMAL | `->>>,>>>,>>>,>>9.99` | 2 | Y | `0` | Amount | Amount transferred | default (data-model §1.5) |
| 9 | `TransferDateTime` | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `?` (unknown) | Transfer Date Time | When the transfer was made | default (data-model §1.5) |
| 10 | `DebitTransactionId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Debit Transaction Id | Reference to [DebitTransaction](DebitTransaction.md).`DebitTransactionId` | Random existing parent row, respecting the cardinality |
| 11 | `CreditTransactionId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Credit Transaction Id | Reference to [CreditTransaction](CreditTransaction.md).`CreditTransactionId` | Random existing parent row, respecting the cardinality |
| 12 | `TransferStatus` | CHARACTER | `x(10)` |  | Y | `POSTED` | Transfer Status | Lifecycle status | Always POSTED at load |
| 13 | `Channel` | CHARACTER | `x(8)` |  | Y | `ONLINE` | Channel | ONLINE, MOBILE, BRANCH | ONLINE, MOBILE, BRANCH |

## Indexes

7 indexes (3 table-specific).

| Name | Components | Primary | Unique | Word | Purpose |
|---|---|---|---|---|---|
| `PkTransfer` *(std)* | TransferId ASC | Y | Y | N | Single-row random access by sequential ID; default scan order |
| `IxRandomInt10` *(std)* | RandomInt10 ASC, TransferId ASC | N | N | N | Select ≈ 10% of rows (RandomInt10 = k) |
| `IxRandomInt100` *(std)* | RandomInt100 ASC, TransferId ASC | N | N | N | Select ≈ 1% of rows (RandomInt100 = k) |
| `IxRandomInt1000` *(std)* | RandomInt1000 ASC, TransferId ASC | N | N | N | Select ≈ 0.1% of rows (RandomInt1000 = k) |
| `IxFromAccount` | FromAccountId ASC, TransferDateTime ASC | N | N | N | Outgoing transfers |
| `IxToAccount` | ToAccountId ASC, TransferDateTime ASC | N | N | N | Incoming transfers |
| `UxDebitTransaction` | DebitTransactionId ASC | N | Y | N | Reverse link from a debit |

## Relationships

**Parents**

- `FromAccountId` → [Account](Account.md).`AccountId` — 4 / 0–50 children per parent
- `ToAccountId` → [Account](Account.md).`AccountId` — 4 / 0–50 children per parent
- `DebitTransactionId` → [DebitTransaction](DebitTransaction.md).`DebitTransactionId` — 0.12 / 0–1 children per parent
- `CreditTransactionId` → [CreditTransaction](CreditTransaction.md).`CreditTransactionId` — 0.33 / 0–1 children per parent; not indexed: Reverse lookup handled through the debit side

**Children**

- none

## Access examples

ABL: about 1% of rows, then one random existing row.

```abl
FOR EACH Transfer NO-LOCK WHERE Transfer.RandomInt100 = 42 USE-INDEX IxRandomInt100:
    /* work */
END.

DEFINE VARIABLE r AS INT64 NO-UNDO.
FIND BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.TableName = "Transfer".
r = RANDOM(1, INTEGER(BenchmarkTableInfo.MaxId)).
FIND Transfer NO-LOCK WHERE Transfer.TransferId = r NO-ERROR.   /* not AVAILABLE => draw again */
```

SQL:

```sql
SELECT * FROM PUB.Transfer WHERE RandomInt100 = 42;
SELECT MaxId FROM PUB.BenchmarkTableInfo WHERE TableName = 'Transfer';
SELECT * FROM PUB.Transfer WHERE TransferId = ?;   -- ? drawn uniformly from 1..MaxId
```
