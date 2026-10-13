# InterestRateHistory

`Class R (Reference)` · `Small` · `Narrow` · `LOB: none`

[← Schema overview](../README.md)

## Description

Rate changes per account type over time.

## Facts

| Property | Value |
|---|---|
| Rows at scale factor 1 | 2,880 |
| Scaling | fixed (does not change with scale factor) |
| Volume tier | Small |
| Estimated average record | 60 bytes (field-by-field estimate: 62 bytes) |
| Record-size tier | Narrow |
| Estimated data at SF 1 | 0.000 GB |
| Data area | `PB_Ref_Data` (RPB 64, BPC 8) |
| Index area | `PB_Ref_Idx` (BPC 8) |
| Sequence | `SeqInterestRateHistoryId` (INT64, starts at 1, increment 1, no cycle) |

## Fields

9 fields. *(std)* marks the standard fields present on every table.

| # | Name | Type | Format | Decimals | Mandatory | Initial | Label | Description | Generation |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `InterestRateHistoryId` *(std)* | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Interest Rate History Id | Dense sequential identifier, 1..N with no gaps after the initial load. Runtime inserts use NEXT-VALUE(SeqInterestRateHistoryId). | Assigned 1..N in load order |
| 2 | `RandomInt10` *(std)* | INTEGER | `>9` |  | Y | `0` | Random Int 10 | Independent uniform random value 1–10 for selecting ≈ 10% subsets. 0 = unassigned (invalid). | Independent uniform 1–10; 0 = unassigned (invalid) |
| 3 | `RandomInt100` *(std)* | INTEGER | `>>9` |  | Y | `0` | Random Int 100 | Independent uniform random value 1–100 for selecting ≈ 1% subsets. 0 = unassigned (invalid). | Independent uniform 1–100; 0 = unassigned (invalid) |
| 4 | `RandomInt1000` *(std)* | INTEGER | `>>>9` |  | Y | `0` | Random Int 1000 | Independent uniform random value 1–1000 for selecting ≈ 0.1% subsets. 0 = unassigned (invalid). | Independent uniform 1–1000; 0 = unassigned (invalid) |
| 5 | `CreatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Created At | When the row was created. For historical rows, a synthetic timestamp consistent with the row's business date. | Consistent with the row's business date; NOW for runtime inserts |
| 6 | `AccountTypeId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Account Type Id | Reference to [AccountType](AccountType.md).`AccountTypeId` | Random existing parent row, respecting the cardinality |
| 7 | `EffectiveDate` | DATE | `99/99/9999` |  | Y | `?` (unknown) | Effective Date | Date the rate took effect | First of each month, for 10 years |
| 8 | `InterestRate` | DECIMAL | `>>9.9999` | 4 | Y | `0` | Interest Rate | Annual interest rate (%) | 0.0000–6.0000 |
| 9 | `ChangedByEmployeeId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Changed By Employee Id | Reference to [Employee](Employee.md).`EmployeeId` | Random existing parent row, respecting the cardinality |

## Indexes

5 indexes (1 table-specific).

| Name | Components | Primary | Unique | Word | Purpose |
|---|---|---|---|---|---|
| `PkInterestRateHistory` *(std)* | InterestRateHistoryId ASC | Y | Y | N | Single-row random access by sequential ID; default scan order |
| `IxRandomInt10` *(std)* | RandomInt10 ASC, InterestRateHistoryId ASC | N | N | N | Select ≈ 10% of rows (RandomInt10 = k) |
| `IxRandomInt100` *(std)* | RandomInt100 ASC, InterestRateHistoryId ASC | N | N | N | Select ≈ 1% of rows (RandomInt100 = k) |
| `IxRandomInt1000` *(std)* | RandomInt1000 ASC, InterestRateHistoryId ASC | N | N | N | Select ≈ 0.1% of rows (RandomInt1000 = k) |
| `UxTypeEffective` | AccountTypeId ASC, EffectiveDate DESC | N | Y | N | Rate in effect on a date |

## Relationships

**Parents**

- `AccountTypeId` → [AccountType](AccountType.md).`AccountTypeId` — 120 / 120–120 children per parent
- `ChangedByEmployeeId` → [Employee](Employee.md).`EmployeeId` — 0.6 / 0–10 children per parent; not indexed: Audit-only reference

**Children**

- none

## Access examples

ABL: about 1% of rows, then one random existing row.

```abl
FOR EACH InterestRateHistory NO-LOCK WHERE InterestRateHistory.RandomInt100 = 42 USE-INDEX IxRandomInt100:
    /* work */
END.

DEFINE VARIABLE r AS INT64 NO-UNDO.
FIND BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.TableName = "InterestRateHistory".
r = RANDOM(1, INTEGER(BenchmarkTableInfo.MaxId)).
FIND InterestRateHistory NO-LOCK WHERE InterestRateHistory.InterestRateHistoryId = r NO-ERROR.   /* not AVAILABLE => draw again */
```

SQL:

```sql
SELECT * FROM PUB.InterestRateHistory WHERE RandomInt100 = 42;
SELECT MaxId FROM PUB.BenchmarkTableInfo WHERE TableName = 'InterestRateHistory';
SELECT * FROM PUB.InterestRateHistory WHERE InterestRateHistoryId = ?;   -- ? drawn uniformly from 1..MaxId
```
