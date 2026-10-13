# AccountType

`Class R (Reference)` · `Tiny` · `Wide` · `LOB: none`

[← Schema overview](../README.md)

## Description

Product definitions (checking, savings, CD…).

## Facts

| Property | Value |
|---|---|
| Rows at scale factor 1 | 24 |
| Scaling | fixed (does not change with scale factor) |
| Volume tier | Tiny |
| Estimated average record | 1,500 bytes (field-by-field estimate: 812 bytes) |
| Record-size tier | Wide |
| Estimated data at SF 1 | 0.000 GB |
| Data area | `PB_Ref_Data` (RPB 64, BPC 8) |
| Index area | `PB_Ref_Idx` (BPC 8) |
| Sequence | `SeqAccountTypeId` (INT64, starts at 1, increment 1, no cycle) |

## Fields

16 fields. *(std)* marks the standard fields present on every table.

| # | Name | Type | Format | Decimals | Mandatory | Initial | Label | Description | Generation |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `AccountTypeId` *(std)* | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Account Type Id | Dense sequential identifier, 1..N with no gaps after the initial load. Runtime inserts use NEXT-VALUE(SeqAccountTypeId). | Assigned 1..N in load order |
| 2 | `RandomInt10` *(std)* | INTEGER | `>9` |  | Y | `0` | Random Int 10 | Independent uniform random value 1–10 for selecting ≈ 10% subsets. 0 = unassigned (invalid). | Independent uniform 1–10; 0 = unassigned (invalid) |
| 3 | `RandomInt100` *(std)* | INTEGER | `>>9` |  | Y | `0` | Random Int 100 | Independent uniform random value 1–100 for selecting ≈ 1% subsets. 0 = unassigned (invalid). | Independent uniform 1–100; 0 = unassigned (invalid) |
| 4 | `RandomInt1000` *(std)* | INTEGER | `>>>9` |  | Y | `0` | Random Int 1000 | Independent uniform random value 1–1000 for selecting ≈ 0.1% subsets. 0 = unassigned (invalid). | Independent uniform 1–1000; 0 = unassigned (invalid) |
| 5 | `CreatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Created At | When the row was created. For historical rows, a synthetic timestamp consistent with the row's business date. | Consistent with the row's business date; NOW for runtime inserts |
| 6 | `AccountTypeCode` | CHARACTER | `x(10)` |  | Y | `""` | Account Type Code | e.g. CHKBASIC, SAVHIYLD, CD12M | e.g. CHKBASIC, SAVHIYLD, CD12M |
| 7 | `AccountTypeName` | CHARACTER | `x(50)` |  | Y | `""` | Account Type Name | Product name | default (data-model §1.5) |
| 8 | `Category` | CHARACTER | `x(12)` |  | Y | `""` | Category | CHECKING, SAVINGS, MONEYMARKET, CD | CHECKING, SAVINGS, MONEYMARKET, CD |
| 9 | `Description` | CHARACTER | `x(200)` |  | Y | `""` | Description | Human-readable description | default (data-model §1.5) |
| 10 | `TermsText` | CHARACTER | `x(1200)` |  | Y | `""` | Terms Text | Plain-text terms, 900–1,200 characters (makes the record Wide without a LOB) | Plain-text terms, 900–1,200 characters (makes the record Wide without a LOB) |
| 11 | `MinimumBalance` | DECIMAL | `->>>,>>>,>>>,>>9.99` | 2 | Y | `0` | Minimum Balance | Minimum balance | default (data-model §1.5) |
| 12 | `MonthlyFee` | DECIMAL | `->>>,>>>,>>>,>>9.99` | 2 | Y | `0` | Monthly Fee | Monthly maintenance fee | default (data-model §1.5) |
| 13 | `OverdraftAllowed` | LOGICAL | `yes/no` |  | Y | `no` | Overdraft Allowed | Whether overdraft is allowed | default (data-model §1.5) |
| 14 | `TermMonths` | INTEGER | `>>9` |  | Y | `0` | Term Months | Term in months | 0 unless CD (3–60) |
| 15 | `CurrentInterestRate` | DECIMAL | `>>9.9999` | 4 | Y | `0` | Current Interest Rate | Equals the latest InterestRateHistory row | Equals the latest InterestRateHistory row |
| 16 | `IsActive` | LOGICAL | `yes/no` |  | Y | `yes` | Is Active | Whether the row is active | default (data-model §1.5) |

## Indexes

6 indexes (2 table-specific).

| Name | Components | Primary | Unique | Word | Purpose |
|---|---|---|---|---|---|
| `PkAccountType` *(std)* | AccountTypeId ASC | Y | Y | N | Single-row random access by sequential ID; default scan order |
| `IxRandomInt10` *(std)* | RandomInt10 ASC, AccountTypeId ASC | N | N | N | Select ≈ 10% of rows (RandomInt10 = k) |
| `IxRandomInt100` *(std)* | RandomInt100 ASC, AccountTypeId ASC | N | N | N | Select ≈ 1% of rows (RandomInt100 = k) |
| `IxRandomInt1000` *(std)* | RandomInt1000 ASC, AccountTypeId ASC | N | N | N | Select ≈ 0.1% of rows (RandomInt1000 = k) |
| `UxAccountTypeCode` | AccountTypeCode ASC | N | Y | N | Lookup |
| `IxCategory` | Category ASC | N | N | N | Products by category |

## Relationships

**Parents**

- none

**Children**

- [InterestRateHistory](InterestRateHistory.md).`AccountTypeId`
- [Account](Account.md).`AccountTypeId`

## Access examples

ABL: about 1% of rows, then one random existing row.

```abl
FOR EACH AccountType NO-LOCK WHERE AccountType.RandomInt100 = 42 USE-INDEX IxRandomInt100:
    /* work */
END.

DEFINE VARIABLE r AS INT64 NO-UNDO.
FIND BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.TableName = "AccountType".
r = RANDOM(1, INTEGER(BenchmarkTableInfo.MaxId)).
FIND AccountType NO-LOCK WHERE AccountType.AccountTypeId = r NO-ERROR.   /* not AVAILABLE => draw again */
```

SQL:

```sql
SELECT * FROM PUB.AccountType WHERE RandomInt100 = 42;
SELECT MaxId FROM PUB.BenchmarkTableInfo WHERE TableName = 'AccountType';
SELECT * FROM PUB.AccountType WHERE AccountTypeId = ?;   -- ? drawn uniformly from 1..MaxId
```
