# LoanPayment

`Class T (Transactional)` · `Large` · `Narrow` · `LOB: none`

[← Schema overview](../README.md)

## Description

Payments against a loan.

## Facts

| Property | Value |
|---|---|
| Rows at scale factor 1 | 6,000,000 |
| Scaling | linear (rows × scale factor) |
| Volume tier | Large |
| Estimated average record | 100 bytes (field-by-field estimate: 96 bytes) |
| Record-size tier | Narrow |
| Estimated data at SF 1 | 0.600 GB |
| Data area | `PB_Txn_Large` (RPB 32, BPC 512) |
| Index area | `PB_Txn_Idx` (BPC 512) |
| Sequence | `SeqLoanPaymentId` (INT64, starts at 1, increment 1, no cycle) |

## Fields

13 fields. *(std)* marks the standard fields present on every table.

| # | Name | Type | Format | Decimals | Mandatory | Initial | Label | Description | Generation |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `LoanPaymentId` *(std)* | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Loan Payment Id | Dense sequential identifier, 1..N with no gaps after the initial load. Runtime inserts use NEXT-VALUE(SeqLoanPaymentId). | Assigned 1..N in load order |
| 2 | `RandomInt10` *(std)* | INTEGER | `>9` |  | Y | `0` | Random Int 10 | Independent uniform random value 1–10 for selecting ≈ 10% subsets. 0 = unassigned (invalid). | Independent uniform 1–10; 0 = unassigned (invalid) |
| 3 | `RandomInt100` *(std)* | INTEGER | `>>9` |  | Y | `0` | Random Int 100 | Independent uniform random value 1–100 for selecting ≈ 1% subsets. 0 = unassigned (invalid). | Independent uniform 1–100; 0 = unassigned (invalid) |
| 4 | `RandomInt1000` *(std)* | INTEGER | `>>>9` |  | Y | `0` | Random Int 1000 | Independent uniform random value 1–1000 for selecting ≈ 0.1% subsets. 0 = unassigned (invalid). | Independent uniform 1–1000; 0 = unassigned (invalid) |
| 5 | `CreatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Created At | When the row was created. For historical rows, a synthetic timestamp consistent with the row's business date. | Consistent with the row's business date; NOW for runtime inserts |
| 6 | `LoanId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Loan Id | Reference to [Loan](Loan.md).`LoanId` | Random existing parent row, respecting the cardinality |
| 7 | `DueDate` | DATE | `99/99/9999` |  | Y | `?` (unknown) | Due Date | Payment due date | Monthly |
| 8 | `PaymentDate` | DATE | `99/99/9999` |  | Y | `?` (unknown) | Payment Date | Date the payment was made | DueDate −5 to +20 days |
| 9 | `AmountPaid` | DECIMAL | `->>>,>>>,>>>,>>9.99` | 2 | Y | `0` | Amount Paid | Total amount paid | default (data-model §1.5) |
| 10 | `PrincipalPortion` | DECIMAL | `->>>,>>>,>>>,>>9.99` | 2 | Y | `0` | Principal Portion | Portion of the payment applied to principal | default (data-model §1.5) |
| 11 | `InterestPortion` | DECIMAL | `->>>,>>>,>>>,>>9.99` | 2 | Y | `0` | Interest Portion | Portion of the payment applied to interest | default (data-model §1.5) |
| 12 | `LateFee` | DECIMAL | `->>>,>>>,>>>,>>9.99` | 2 | Y | `0` | Late Fee | Late fee charged | Non-zero when paid more than 10 days late |
| 13 | `DebitTransactionId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Debit Transaction Id | Reference to [DebitTransaction](DebitTransaction.md).`DebitTransactionId` | 0 when paid before the 12-month history window |

## Indexes

6 indexes (2 table-specific).

| Name | Components | Primary | Unique | Word | Purpose |
|---|---|---|---|---|---|
| `PkLoanPayment` *(std)* | LoanPaymentId ASC | Y | Y | N | Single-row random access by sequential ID; default scan order |
| `IxRandomInt10` *(std)* | RandomInt10 ASC, LoanPaymentId ASC | N | N | N | Select ≈ 10% of rows (RandomInt10 = k) |
| `IxRandomInt100` *(std)* | RandomInt100 ASC, LoanPaymentId ASC | N | N | N | Select ≈ 1% of rows (RandomInt100 = k) |
| `IxRandomInt1000` *(std)* | RandomInt1000 ASC, LoanPaymentId ASC | N | N | N | Select ≈ 0.1% of rows (RandomInt1000 = k) |
| `IxLoanPayment` | LoanId ASC, PaymentDate DESC | N | N | N | Payment history |
| `IxDueDate` | DueDate ASC | N | N | N | Delinquency reporting |

## Relationships

**Parents**

- `LoanId` → [Loan](Loan.md).`LoanId` — 24 / 1–60 children per parent
- `DebitTransactionId` → [DebitTransaction](DebitTransaction.md).`DebitTransactionId` — 0.06 / 0–1 children per parent; optional (0 = none); not indexed: Lookup to DebitTransaction only

**Children**

- none

## Access examples

ABL: about 1% of rows, then one random existing row.

```abl
FOR EACH LoanPayment NO-LOCK WHERE LoanPayment.RandomInt100 = 42 USE-INDEX IxRandomInt100:
    /* work */
END.

DEFINE VARIABLE r AS INT64 NO-UNDO.
FIND BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.TableName = "LoanPayment".
r = RANDOM(1, INTEGER(BenchmarkTableInfo.MaxId)).
FIND LoanPayment NO-LOCK WHERE LoanPayment.LoanPaymentId = r NO-ERROR.   /* not AVAILABLE => draw again */
```

SQL:

```sql
SELECT * FROM PUB.LoanPayment WHERE RandomInt100 = 42;
SELECT MaxId FROM PUB.BenchmarkTableInfo WHERE TableName = 'LoanPayment';
SELECT * FROM PUB.LoanPayment WHERE LoanPaymentId = ?;   -- ? drawn uniformly from 1..MaxId
```
