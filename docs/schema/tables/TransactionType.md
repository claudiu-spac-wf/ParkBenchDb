# TransactionType

`Class R (Reference)` · `Tiny` · `Narrow` · `LOB: none`

[← Schema overview](../README.md)

## Description

Codes for debit/credit kinds (ATM, POS, ACH, fee…).

## Facts

| Property | Value |
|---|---|
| Rows at scale factor 1 | 60 |
| Scaling | fixed (does not change with scale factor) |
| Volume tier | Tiny |
| Estimated average record | 110 bytes (field-by-field estimate: 86 bytes) |
| Record-size tier | Narrow |
| Estimated data at SF 1 | 0.000 GB |
| Data area | `PB_Ref_Data` (RPB 64, BPC 8) |
| Index area | `PB_Ref_Idx` (BPC 8) |
| Sequence | `SeqTransactionTypeId` (INT64, starts at 1, increment 1, no cycle) |

## Fields

10 fields. *(std)* marks the standard fields present on every table.

| # | Name | Type | Format | Decimals | Mandatory | Initial | Label | Description | Generation |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `TransactionTypeId` *(std)* | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Transaction Type Id | Dense sequential identifier, 1..N with no gaps after the initial load. Runtime inserts use NEXT-VALUE(SeqTransactionTypeId). | Assigned 1..N in load order |
| 2 | `RandomInt10` *(std)* | INTEGER | `>9` |  | Y | `0` | Random Int 10 | Independent uniform random value 1–10 for selecting ≈ 10% subsets. 0 = unassigned (invalid). | Independent uniform 1–10; 0 = unassigned (invalid) |
| 3 | `RandomInt100` *(std)* | INTEGER | `>>9` |  | Y | `0` | Random Int 100 | Independent uniform random value 1–100 for selecting ≈ 1% subsets. 0 = unassigned (invalid). | Independent uniform 1–100; 0 = unassigned (invalid) |
| 4 | `RandomInt1000` *(std)* | INTEGER | `>>>9` |  | Y | `0` | Random Int 1000 | Independent uniform random value 1–1000 for selecting ≈ 0.1% subsets. 0 = unassigned (invalid). | Independent uniform 1–1000; 0 = unassigned (invalid) |
| 5 | `CreatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Created At | When the row was created. For historical rows, a synthetic timestamp consistent with the row's business date. | Consistent with the row's business date; NOW for runtime inserts |
| 6 | `TransactionTypeCode` | CHARACTER | `x(8)` |  | Y | `""` | Transaction Type Code | e.g. POS, ATMWD, ACHCR, FEEMNT | e.g. POS, ATMWD, ACHCR, FEEMNT |
| 7 | `Description` | CHARACTER | `x(60)` |  | Y | `""` | Description | Human-readable description | default (data-model §1.5) |
| 8 | `Direction` | CHARACTER | `x(1)` |  | Y | `""` | Direction | D debit, C credit | D debit, C credit |
| 9 | `Channel` | CHARACTER | `x(10)` |  | Y | `""` | Channel | ATM, POS, ACH, WIRE, BRANCH, ONLINE, INTERNAL | ATM, POS, ACH, WIRE, BRANCH, ONLINE, INTERNAL |
| 10 | `IsFee` | LOGICAL | `yes/no` |  | Y | `no` | Is Fee | Whether this type is a fee | default (data-model §1.5) |

## Indexes

6 indexes (2 table-specific).

| Name | Components | Primary | Unique | Word | Purpose |
|---|---|---|---|---|---|
| `PkTransactionType` *(std)* | TransactionTypeId ASC | Y | Y | N | Single-row random access by sequential ID; default scan order |
| `IxRandomInt10` *(std)* | RandomInt10 ASC, TransactionTypeId ASC | N | N | N | Select ≈ 10% of rows (RandomInt10 = k) |
| `IxRandomInt100` *(std)* | RandomInt100 ASC, TransactionTypeId ASC | N | N | N | Select ≈ 1% of rows (RandomInt100 = k) |
| `IxRandomInt1000` *(std)* | RandomInt1000 ASC, TransactionTypeId ASC | N | N | N | Select ≈ 0.1% of rows (RandomInt1000 = k) |
| `UxTransactionTypeCode` | TransactionTypeCode ASC | N | Y | N | Lookup |
| `IxDirectionChannel` | Direction ASC, Channel ASC | N | N | N | Types by direction |

## Relationships

**Parents**

- none

**Children**

- [CreditTransaction](CreditTransaction.md).`TransactionTypeId`
- [DebitTransaction](DebitTransaction.md).`TransactionTypeId`

## Access examples

ABL: about 1% of rows, then one random existing row.

```abl
FOR EACH TransactionType NO-LOCK WHERE TransactionType.RandomInt100 = 42 USE-INDEX IxRandomInt100:
    /* work */
END.

DEFINE VARIABLE r AS INT64 NO-UNDO.
FIND BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.TableName = "TransactionType".
r = RANDOM(1, INTEGER(BenchmarkTableInfo.MaxId)).
FIND TransactionType NO-LOCK WHERE TransactionType.TransactionTypeId = r NO-ERROR.   /* not AVAILABLE => draw again */
```

SQL:

```sql
SELECT * FROM PUB.TransactionType WHERE RandomInt100 = 42;
SELECT MaxId FROM PUB.BenchmarkTableInfo WHERE TableName = 'TransactionType';
SELECT * FROM PUB.TransactionType WHERE TransactionTypeId = ?;   -- ? drawn uniformly from 1..MaxId
```
