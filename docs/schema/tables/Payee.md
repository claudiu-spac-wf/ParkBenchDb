# Payee

`Class M (Master)` · `Medium` · `Standard` · `LOB: none`

[← Schema overview](../README.md)

## Description

Saved beneficiaries for payments.

## Facts

| Property | Value |
|---|---|
| Rows at scale factor 1 | 2,500,000 |
| Scaling | linear (rows × scale factor) |
| Volume tier | Medium |
| Estimated average record | 250 bytes (field-by-field estimate: 245 bytes) |
| Record-size tier | Standard |
| Estimated data at SF 1 | 0.625 GB |
| Data area | `PB_Master_Std` (RPB 16, BPC 64) |
| Index area | `PB_Master_Idx` (BPC 64) |
| Sequence | `SeqPayeeId` (INT64, starts at 1, increment 1, no cycle) |

## Fields

18 fields. *(std)* marks the standard fields present on every table.

| # | Name | Type | Format | Decimals | Mandatory | Initial | Label | Description | Generation |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `PayeeId` *(std)* | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Payee Id | Dense sequential identifier, 1..N with no gaps after the initial load. Runtime inserts use NEXT-VALUE(SeqPayeeId). | Assigned 1..N in load order |
| 2 | `RandomInt10` *(std)* | INTEGER | `>9` |  | Y | `0` | Random Int 10 | Independent uniform random value 1–10 for selecting ≈ 10% subsets. 0 = unassigned (invalid). | Independent uniform 1–10; 0 = unassigned (invalid) |
| 3 | `RandomInt100` *(std)* | INTEGER | `>>9` |  | Y | `0` | Random Int 100 | Independent uniform random value 1–100 for selecting ≈ 1% subsets. 0 = unassigned (invalid). | Independent uniform 1–100; 0 = unassigned (invalid) |
| 4 | `RandomInt1000` *(std)* | INTEGER | `>>>9` |  | Y | `0` | Random Int 1000 | Independent uniform random value 1–1000 for selecting ≈ 0.1% subsets. 0 = unassigned (invalid). | Independent uniform 1–1000; 0 = unassigned (invalid) |
| 5 | `CreatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Created At | When the row was created. For historical rows, a synthetic timestamp consistent with the row's business date. | Consistent with the row's business date; NOW for runtime inserts |
| 6 | `CustomerId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Customer Id | Reference to [Customer](Customer.md).`CustomerId` | Random existing parent row, respecting the cardinality |
| 7 | `PayeeName` | CHARACTER | `x(80)` |  | Y | `""` | Payee Name | Name of the payee | default (data-model §1.5) |
| 8 | `PayeeKind` | CHARACTER | `x(10)` |  | Y | `""` | Payee Kind | Kind of payee | BILLER, PERSON, BUSINESS |
| 9 | `BankRoutingNumber` | CHARACTER | `x(9)` |  | Y | `""` | Bank Routing Number | Payee bank routing number | default (data-model §1.5) |
| 10 | `AccountNumberMasked` | CHARACTER | `x(20)` |  | Y | `""` | Account Number Masked | Masked payee account number | default (data-model §1.5) |
| 11 | `ReferenceText` | CHARACTER | `x(40)` |  | Y | `""` | Reference Text | Customer's account number at the biller | Customer's account number at the biller |
| 12 | `Email` | CHARACTER | `x(80)` |  | Y | `""` | Email | Email address | 40% populated |
| 13 | `AddressLine1` | CHARACTER | `x(60)` |  | Y | `""` | Address Line 1 | First address line | default (data-model §1.5) |
| 14 | `City` | CHARACTER | `x(40)` |  | Y | `""` | City | City name | default (data-model §1.5) |
| 15 | `PostalCode` | CHARACTER | `x(10)` |  | Y | `""` | Postal Code | Postal / ZIP code | default (data-model §1.5) |
| 16 | `IsFavorite` | LOGICAL | `yes/no` |  | Y | `no` | Is Favorite | Marked as a favourite by the customer | 20% yes |
| 17 | `LastPaidDate` | DATE | `99/99/9999` |  | N | `?` (unknown) | Last Paid Date | Date of the last payment to this payee | default (data-model §1.5) |
| 18 | `UpdatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Updated At | Last modification time; equals CreatedAt right after the load. | Equal to CreatedAt at load |

## Indexes

5 indexes (1 table-specific).

| Name | Components | Primary | Unique | Word | Purpose |
|---|---|---|---|---|---|
| `PkPayee` *(std)* | PayeeId ASC | Y | Y | N | Single-row random access by sequential ID; default scan order |
| `IxRandomInt10` *(std)* | RandomInt10 ASC, PayeeId ASC | N | N | N | Select ≈ 10% of rows (RandomInt10 = k) |
| `IxRandomInt100` *(std)* | RandomInt100 ASC, PayeeId ASC | N | N | N | Select ≈ 1% of rows (RandomInt100 = k) |
| `IxRandomInt1000` *(std)* | RandomInt1000 ASC, PayeeId ASC | N | N | N | Select ≈ 0.1% of rows (RandomInt1000 = k) |
| `IxCustomerName` | CustomerId ASC, PayeeName ASC | N | N | N | A customer's payees, alphabetical |

## Relationships

**Parents**

- `CustomerId` → [Customer](Customer.md).`CustomerId` — 2.5 / 0–25 children per parent

**Children**

- [ScheduledPayment](ScheduledPayment.md).`PayeeId`

## Access examples

ABL: about 1% of rows, then one random existing row.

```abl
FOR EACH Payee NO-LOCK WHERE Payee.RandomInt100 = 42 USE-INDEX IxRandomInt100:
    /* work */
END.

DEFINE VARIABLE r AS INT64 NO-UNDO.
FIND BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.TableName = "Payee".
r = RANDOM(1, INTEGER(BenchmarkTableInfo.MaxId)).
FIND Payee NO-LOCK WHERE Payee.PayeeId = r NO-ERROR.   /* not AVAILABLE => draw again */
```

SQL:

```sql
SELECT * FROM PUB.Payee WHERE RandomInt100 = 42;
SELECT MaxId FROM PUB.BenchmarkTableInfo WHERE TableName = 'Payee';
SELECT * FROM PUB.Payee WHERE PayeeId = ?;   -- ? drawn uniformly from 1..MaxId
```
