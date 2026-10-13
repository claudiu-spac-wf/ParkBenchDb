# Branch

`Class R (Reference)` · `Tiny` · `Standard` · `LOB: none`

[← Schema overview](../README.md)

## Description

Physical bank branch.

## Facts

| Property | Value |
|---|---|
| Rows at scale factor 1 | 250 |
| Scaling | fixed (does not change with scale factor) |
| Volume tier | Tiny |
| Estimated average record | 300 bytes (field-by-field estimate: 168 bytes) |
| Record-size tier | Standard |
| Estimated data at SF 1 | 0.000 GB |
| Data area | `PB_Ref_Data` (RPB 64, BPC 8) |
| Index area | `PB_Ref_Idx` (BPC 8) |
| Sequence | `SeqBranchId` (INT64, starts at 1, increment 1, no cycle) |

## Fields

15 fields. *(std)* marks the standard fields present on every table.

| # | Name | Type | Format | Decimals | Mandatory | Initial | Label | Description | Generation |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `BranchId` *(std)* | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Branch Id | Dense sequential identifier, 1..N with no gaps after the initial load. Runtime inserts use NEXT-VALUE(SeqBranchId). | Assigned 1..N in load order |
| 2 | `RandomInt10` *(std)* | INTEGER | `>9` |  | Y | `0` | Random Int 10 | Independent uniform random value 1–10 for selecting ≈ 10% subsets. 0 = unassigned (invalid). | Independent uniform 1–10; 0 = unassigned (invalid) |
| 3 | `RandomInt100` *(std)* | INTEGER | `>>9` |  | Y | `0` | Random Int 100 | Independent uniform random value 1–100 for selecting ≈ 1% subsets. 0 = unassigned (invalid). | Independent uniform 1–100; 0 = unassigned (invalid) |
| 4 | `RandomInt1000` *(std)* | INTEGER | `>>>9` |  | Y | `0` | Random Int 1000 | Independent uniform random value 1–1000 for selecting ≈ 0.1% subsets. 0 = unassigned (invalid). | Independent uniform 1–1000; 0 = unassigned (invalid) |
| 5 | `CreatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Created At | When the row was created. For historical rows, a synthetic timestamp consistent with the row's business date. | Consistent with the row's business date; NOW for runtime inserts |
| 6 | `BranchCode` | CHARACTER | `x(6)` |  | Y | `""` | Branch Code | Branch business key | B + 5 digits |
| 7 | `BranchName` | CHARACTER | `x(60)` |  | Y | `""` | Branch Name | Branch name | City + suffix (Main St, Downtown, …) |
| 8 | `AddressLine1` | CHARACTER | `x(60)` |  | Y | `""` | Address Line 1 | First address line | default (data-model §1.5) |
| 9 | `City` | CHARACTER | `x(40)` |  | Y | `""` | City | City name | default (data-model §1.5) |
| 10 | `StateProvince` | CHARACTER | `x(30)` |  | Y | `""` | State Province | State or province | default (data-model §1.5) |
| 11 | `PostalCode` | CHARACTER | `x(10)` |  | Y | `""` | Postal Code | Postal / ZIP code | default (data-model §1.5) |
| 12 | `CountryCode` | CHARACTER | `x(2)` |  | Y | `""` | Country Code | ISO country code → [Country](Country.md).`CountryCode` | 90% US |
| 13 | `Phone` | CHARACTER | `x(20)` |  | Y | `""` | Phone | Telephone number | default (data-model §1.5) |
| 14 | `OpenDate` | DATE | `99/99/9999` |  | Y | `?` (unknown) | Open Date | Date opened | 1950–2024 |
| 15 | `IsActive` | LOGICAL | `yes/no` |  | Y | `yes` | Is Active | Whether the row is active | 96% yes |

## Indexes

6 indexes (2 table-specific).

| Name | Components | Primary | Unique | Word | Purpose |
|---|---|---|---|---|---|
| `PkBranch` *(std)* | BranchId ASC | Y | Y | N | Single-row random access by sequential ID; default scan order |
| `IxRandomInt10` *(std)* | RandomInt10 ASC, BranchId ASC | N | N | N | Select ≈ 10% of rows (RandomInt10 = k) |
| `IxRandomInt100` *(std)* | RandomInt100 ASC, BranchId ASC | N | N | N | Select ≈ 1% of rows (RandomInt100 = k) |
| `IxRandomInt1000` *(std)* | RandomInt1000 ASC, BranchId ASC | N | N | N | Select ≈ 0.1% of rows (RandomInt1000 = k) |
| `UxBranchCode` | BranchCode ASC | N | Y | N | Lookup by code |
| `IxCountryCity` | CountryCode ASC, City ASC | N | N | N | Branch locator |

## Relationships

**Parents**

- `CountryCode` → [Country](Country.md).`CountryCode` — 1 / 0–225 (US 90%) children per parent

**Children**

- [Employee](Employee.md).`BranchId`
- [Customer](Customer.md).`HomeBranchId`
- [Account](Account.md).`BranchId`

## Access examples

ABL: about 1% of rows, then one random existing row.

```abl
FOR EACH Branch NO-LOCK WHERE Branch.RandomInt100 = 42 USE-INDEX IxRandomInt100:
    /* work */
END.

DEFINE VARIABLE r AS INT64 NO-UNDO.
FIND BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.TableName = "Branch".
r = RANDOM(1, INTEGER(BenchmarkTableInfo.MaxId)).
FIND Branch NO-LOCK WHERE Branch.BranchId = r NO-ERROR.   /* not AVAILABLE => draw again */
```

SQL:

```sql
SELECT * FROM PUB.Branch WHERE RandomInt100 = 42;
SELECT MaxId FROM PUB.BenchmarkTableInfo WHERE TableName = 'Branch';
SELECT * FROM PUB.Branch WHERE BranchId = ?;   -- ? drawn uniformly from 1..MaxId
```
