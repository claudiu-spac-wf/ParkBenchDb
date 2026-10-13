# Loan

`Class M (Master)` · `Medium` · `Wide` · `LOB: none`

[← Schema overview](../README.md)

## Description

Loan agreement.

## Facts

| Property | Value |
|---|---|
| Rows at scale factor 1 | 250,000 |
| Scaling | linear (rows × scale factor) |
| Volume tier | Medium |
| Estimated average record | 900 bytes (field-by-field estimate: 488 bytes) |
| Record-size tier | Wide |
| Estimated data at SF 1 | 0.225 GB |
| Data area | `PB_Master_Wide` (RPB 8, BPC 64) |
| Index area | `PB_Master_Idx` (BPC 64) |
| Sequence | `SeqLoanId` (INT64, starts at 1, increment 1, no cycle) |

## Fields

22 fields. *(std)* marks the standard fields present on every table.

| # | Name | Type | Format | Decimals | Mandatory | Initial | Label | Description | Generation |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `LoanId` *(std)* | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Loan Id | Dense sequential identifier, 1..N with no gaps after the initial load. Runtime inserts use NEXT-VALUE(SeqLoanId). | Assigned 1..N in load order |
| 2 | `RandomInt10` *(std)* | INTEGER | `>9` |  | Y | `0` | Random Int 10 | Independent uniform random value 1–10 for selecting ≈ 10% subsets. 0 = unassigned (invalid). | Independent uniform 1–10; 0 = unassigned (invalid) |
| 3 | `RandomInt100` *(std)* | INTEGER | `>>9` |  | Y | `0` | Random Int 100 | Independent uniform random value 1–100 for selecting ≈ 1% subsets. 0 = unassigned (invalid). | Independent uniform 1–100; 0 = unassigned (invalid) |
| 4 | `RandomInt1000` *(std)* | INTEGER | `>>>9` |  | Y | `0` | Random Int 1000 | Independent uniform random value 1–1000 for selecting ≈ 0.1% subsets. 0 = unassigned (invalid). | Independent uniform 1–1000; 0 = unassigned (invalid) |
| 5 | `CreatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Created At | When the row was created. For historical rows, a synthetic timestamp consistent with the row's business date. | Consistent with the row's business date; NOW for runtime inserts |
| 6 | `LoanNumber` | CHARACTER | `x(14)` |  | Y | `""` | Loan Number | L + 13 digits | L + 13 digits |
| 7 | `CustomerId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Customer Id | Reference to [Customer](Customer.md).`CustomerId` | Random existing parent row, respecting the cardinality |
| 8 | `DisbursementAccountId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Disbursement Account Id | Reference to [Account](Account.md).`AccountId` | payments are also debited from here |
| 9 | `LoanOfficerEmployeeId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Loan Officer Employee Id | Reference to [Employee](Employee.md).`EmployeeId` | Random existing parent row, respecting the cardinality |
| 10 | `LoanKind` | CHARACTER | `x(10)` |  | Y | `""` | Loan Kind | Kind of loan | MORTGAGE 25%, AUTO 35%, PERSONAL 25%, STUDENT 10%, HELOC 5% |
| 11 | `PrincipalAmount` | DECIMAL | `->>>,>>>,>>>,>>9.99` | 2 | Y | `0` | Principal Amount | Original principal | Varies by kind: 2,000–1,500,000 |
| 12 | `InterestRate` | DECIMAL | `>>9.9999` | 4 | Y | `0` | Interest Rate | Annual interest rate (%) | 2.5–24.0 |
| 13 | `TermMonths` | INTEGER | `>>9` |  | Y | `0` | Term Months | Term in months | 12–360 |
| 14 | `OriginationDate` | DATE | `99/99/9999` |  | Y | `?` (unknown) | Origination Date | Date the loan was originated | Within 10 years before the as-of date |
| 15 | `MaturityDate` | DATE | `99/99/9999` |  | Y | `?` (unknown) | Maturity Date | Date the loan matures | Origination + term |
| 16 | `MonthlyPaymentAmount` | DECIMAL | `->>>,>>>,>>>,>>9.99` | 2 | Y | `0` | Monthly Payment Amount | Scheduled monthly payment | Amortization formula |
| 17 | `OutstandingPrincipal` | DECIMAL | `->>>,>>>,>>>,>>9.99` | 2 | Y | `0` | Outstanding Principal | Principal still owed | default (data-model §1.5) |
| 18 | `NextPaymentDate` | DATE | `99/99/9999` |  | N | `?` (unknown) | Next Payment Date | Date the next payment is due | default (data-model §1.5) |
| 19 | `LoanStatus` | CHARACTER | `x(10)` |  | Y | `CURRENT` | Loan Status | Lifecycle status | CURRENT 90%, LATE 5%, DEFAULT 1%, PAIDOFF 4% |
| 20 | `CollateralDescription` | CHARACTER | `x(400)` |  | Y | `""` | Collateral Description | 200–400 characters (width) | 200–400 characters (width) |
| 21 | `UnderwritingNotes` | CHARACTER | `x(300)` |  | Y | `""` | Underwriting Notes | 150–300 characters (width) | 150–300 characters (width) |
| 22 | `UpdatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Updated At | Last modification time; equals CreatedAt right after the load. | Equal to CreatedAt at load |

## Indexes

7 indexes (3 table-specific).

| Name | Components | Primary | Unique | Word | Purpose |
|---|---|---|---|---|---|
| `PkLoan` *(std)* | LoanId ASC | Y | Y | N | Single-row random access by sequential ID; default scan order |
| `IxRandomInt10` *(std)* | RandomInt10 ASC, LoanId ASC | N | N | N | Select ≈ 10% of rows (RandomInt10 = k) |
| `IxRandomInt100` *(std)* | RandomInt100 ASC, LoanId ASC | N | N | N | Select ≈ 1% of rows (RandomInt100 = k) |
| `IxRandomInt1000` *(std)* | RandomInt1000 ASC, LoanId ASC | N | N | N | Select ≈ 0.1% of rows (RandomInt1000 = k) |
| `UxLoanNumber` | LoanNumber ASC | N | Y | N | Lookup |
| `IxCustomer` | CustomerId ASC | N | N | N | A customer's loans |
| `IxStatusNextPayment` | LoanStatus ASC, NextPaymentDate ASC | N | N | N | Billing batch |

## Relationships

**Parents**

- `CustomerId` → [Customer](Customer.md).`CustomerId` — 0.25 / 0–3 children per parent
- `DisbursementAccountId` → [Account](Account.md).`AccountId` — 0.17 / 0–3 children per parent; not indexed: Lookup to Account only
- `LoanOfficerEmployeeId` → [Employee](Employee.md).`EmployeeId` — 50 / 0–400 (loan officers only) children per parent; not indexed: Lookup to Employee only

**Children**

- [LoanPayment](LoanPayment.md).`LoanId`

## Access examples

ABL: about 1% of rows, then one random existing row.

```abl
FOR EACH Loan NO-LOCK WHERE Loan.RandomInt100 = 42 USE-INDEX IxRandomInt100:
    /* work */
END.

DEFINE VARIABLE r AS INT64 NO-UNDO.
FIND BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.TableName = "Loan".
r = RANDOM(1, INTEGER(BenchmarkTableInfo.MaxId)).
FIND Loan NO-LOCK WHERE Loan.LoanId = r NO-ERROR.   /* not AVAILABLE => draw again */
```

SQL:

```sql
SELECT * FROM PUB.Loan WHERE RandomInt100 = 42;
SELECT MaxId FROM PUB.BenchmarkTableInfo WHERE TableName = 'Loan';
SELECT * FROM PUB.Loan WHERE LoanId = ?;   -- ? drawn uniformly from 1..MaxId
```
