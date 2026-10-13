# Customer

`Class M (Master)` · `Medium` · `Wide` · `LOB: none`

[← Schema overview](../README.md)

## Description

Individual or business bank customer.

## Facts

| Property | Value |
|---|---|
| Rows at scale factor 1 | 1,000,000 |
| Scaling | linear (rows × scale factor) |
| Volume tier | Medium |
| Estimated average record | 850 bytes (field-by-field estimate: 515 bytes) |
| Record-size tier | Wide |
| Estimated data at SF 1 | 0.850 GB |
| Data area | `PB_Master_Wide` (RPB 8, BPC 64) |
| Index area | `PB_Master_Idx` (BPC 64) |
| Sequence | `SeqCustomerId` (INT64, starts at 1, increment 1, no cycle) |

## Fields

31 fields. *(std)* marks the standard fields present on every table.

| # | Name | Type | Format | Decimals | Mandatory | Initial | Label | Description | Generation |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `CustomerId` *(std)* | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Customer Id | Dense sequential identifier, 1..N with no gaps after the initial load. Runtime inserts use NEXT-VALUE(SeqCustomerId). | Assigned 1..N in load order |
| 2 | `RandomInt10` *(std)* | INTEGER | `>9` |  | Y | `0` | Random Int 10 | Independent uniform random value 1–10 for selecting ≈ 10% subsets. 0 = unassigned (invalid). | Independent uniform 1–10; 0 = unassigned (invalid) |
| 3 | `RandomInt100` *(std)* | INTEGER | `>>9` |  | Y | `0` | Random Int 100 | Independent uniform random value 1–100 for selecting ≈ 1% subsets. 0 = unassigned (invalid). | Independent uniform 1–100; 0 = unassigned (invalid) |
| 4 | `RandomInt1000` *(std)* | INTEGER | `>>>9` |  | Y | `0` | Random Int 1000 | Independent uniform random value 1–1000 for selecting ≈ 0.1% subsets. 0 = unassigned (invalid). | Independent uniform 1–1000; 0 = unassigned (invalid) |
| 5 | `CreatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Created At | When the row was created. For historical rows, a synthetic timestamp consistent with the row's business date. | Consistent with the row's business date; NOW for runtime inserts |
| 6 | `CustomerNumber` | CHARACTER | `x(12)` |  | Y | `""` | Customer Number | C + 10 digits (random, unique; not the ID) | C + 10 digits (random, unique; not the ID) |
| 7 | `CustomerKind` | CHARACTER | `x(1)` |  | Y | `""` | Customer Kind | I individual 92%, B business 8% | I individual 92%, B business 8% |
| 8 | `FirstName` | CHARACTER | `x(30)` |  | Y | `""` | First Name | Given name | Empty for businesses |
| 9 | `MiddleName` | CHARACTER | `x(30)` |  | Y | `""` | Middle Name | Middle name | 40% populated |
| 10 | `LastName` | CHARACTER | `x(40)` |  | Y | `""` | Last Name | Family name | Business: primary contact's last name |
| 11 | `BusinessName` | CHARACTER | `x(80)` |  | Y | `""` | Business Name | Registered business name | Businesses only |
| 12 | `DateOfBirth` | DATE | `99/99/9999` |  | N | `?` (unknown) | Date Of Birth | Date of birth | Individuals, age 18–95 |
| 13 | `TaxIdMasked` | CHARACTER | `x(11)` |  | Y | `""` | Tax Id Masked | Masked tax identifier | ***-**-1234 |
| 14 | `Email` | CHARACTER | `x(80)` |  | Y | `""` | Email | Email address | default (data-model §1.5) |
| 15 | `PreferredLanguage` | CHARACTER | `x(5)` |  | Y | `en` | Preferred Language | en 85%, es 12%, other 3% | en 85%, es 12%, other 3% |
| 16 | `HomeBranchId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Home Branch Id | Reference to [Branch](Branch.md).`BranchId` | Random existing parent row, respecting the cardinality |
| 17 | `Segment` | CHARACTER | `x(10)` |  | Y | `RETAIL` | Segment | RETAIL 80%, PREMIER 12%, PRIVATE 2%, SMB 6% | RETAIL 80%, PREMIER 12%, PRIVATE 2%, SMB 6% |
| 18 | `CreditScore` | INTEGER | `>>9` |  | Y | `0` | Credit Score | 300–850, normal around 700 | 300–850, normal around 700 |
| 19 | `AnnualIncome` | DECIMAL | `->>>,>>>,>>>,>>9.99` | 2 | Y | `0` | Annual Income | Reported annual income | Log-normal |
| 20 | `CustomerSince` | DATE | `99/99/9999` |  | Y | `?` (unknown) | Customer Since | Date the customer relationship began | 1980 – as-of date |
| 21 | `CustomerStatus` | CHARACTER | `x(10)` |  | Y | `ACTIVE` | Customer Status | Lifecycle status | ACTIVE 90%, DORMANT 7%, CLOSED 3% |
| 22 | `IsPaperless` | LOGICAL | `yes/no` |  | Y | `no` | Is Paperless | Receives statements electronically | 55% yes |
| 23 | `MarketingOptIn` | LOGICAL | `yes/no` |  | Y | `no` | Marketing Opt In | Consented to marketing | 35% yes |
| 24 | `KycVerifiedAt` | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | N | `?` (unknown) | Kyc Verified At | When identity (KYC) was verified | 98% set |
| 25 | `RiskRating` | CHARACTER | `x(1)` |  | Y | `L` | Risk Rating | AML risk rating | L/M/H 80/17/3% |
| 26 | `Occupation` | CHARACTER | `x(40)` |  | Y | `""` | Occupation | Customer occupation | default (data-model §1.5) |
| 27 | `EmployerName` | CHARACTER | `x(60)` |  | Y | `""` | Employer Name | Customer employer | default (data-model §1.5) |
| 28 | `SecurityQuestion` | CHARACTER | `x(100)` |  | Y | `""` | Security Question | One of 10 questions | One of 10 questions |
| 29 | `Preferences` | CHARACTER | `x(300)` |  | Y | `""` | Preferences | key=value; list, 150–300 characters (width filler) | key=value; list, 150–300 characters (width filler) |
| 30 | `LastContactDate` | DATE | `99/99/9999` |  | N | `?` (unknown) | Last Contact Date | Date of the last contact with the customer | default (data-model §1.5) |
| 31 | `UpdatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Updated At | Last modification time; equals CreatedAt right after the load. | Equal to CreatedAt at load |

## Indexes

9 indexes (5 table-specific).

| Name | Components | Primary | Unique | Word | Purpose |
|---|---|---|---|---|---|
| `PkCustomer` *(std)* | CustomerId ASC | Y | Y | N | Single-row random access by sequential ID; default scan order |
| `IxRandomInt10` *(std)* | RandomInt10 ASC, CustomerId ASC | N | N | N | Select ≈ 10% of rows (RandomInt10 = k) |
| `IxRandomInt100` *(std)* | RandomInt100 ASC, CustomerId ASC | N | N | N | Select ≈ 1% of rows (RandomInt100 = k) |
| `IxRandomInt1000` *(std)* | RandomInt1000 ASC, CustomerId ASC | N | N | N | Select ≈ 0.1% of rows (RandomInt1000 = k) |
| `UxCustomerNumber` | CustomerNumber ASC | N | Y | N | Lookup by business key |
| `IxName` | LastName ASC, FirstName ASC | N | N | N | Name search, range scans |
| `IxHomeBranch` | HomeBranchId ASC | N | N | N | Customers per branch |
| `IxStatusSegment` | CustomerStatus ASC, Segment ASC | N | N | N | Low-cardinality index (a known anti-pattern worth benchmarking) |
| `IxEmail` | Email ASC | N | N | N | Login lookup |

## Relationships

**Parents**

- `HomeBranchId` → [Branch](Branch.md).`BranchId` — 4,000 / 500–15,000 children per parent

**Children**

- [CustomerAddress](CustomerAddress.md).`CustomerId`
- [CustomerContact](CustomerContact.md).`CustomerId`
- [CustomerDocument](CustomerDocument.md).`CustomerId`
- [CustomerNote](CustomerNote.md).`CustomerId`
- [AccountHolder](AccountHolder.md).`CustomerId`
- [Payee](Payee.md).`CustomerId`
- [Card](Card.md).`CustomerId`
- [Loan](Loan.md).`CustomerId`
- [LoginEvent](LoginEvent.md).`CustomerId`

## Access examples

ABL: about 1% of rows, then one random existing row.

```abl
FOR EACH Customer NO-LOCK WHERE Customer.RandomInt100 = 42 USE-INDEX IxRandomInt100:
    /* work */
END.

DEFINE VARIABLE r AS INT64 NO-UNDO.
FIND BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.TableName = "Customer".
r = RANDOM(1, INTEGER(BenchmarkTableInfo.MaxId)).
FIND Customer NO-LOCK WHERE Customer.CustomerId = r NO-ERROR.   /* not AVAILABLE => draw again */
```

SQL:

```sql
SELECT * FROM PUB.Customer WHERE RandomInt100 = 42;
SELECT MaxId FROM PUB.BenchmarkTableInfo WHERE TableName = 'Customer';
SELECT * FROM PUB.Customer WHERE CustomerId = ?;   -- ? drawn uniformly from 1..MaxId
```
