# BenchmarkTableInfo

`Class R (Reference)` · `Tiny` · `Narrow` · `LOB: none`

[← Schema overview](../README.md)

## Description

Row counts and max sequential IDs per table.

Written last by the loader. Benchmarks read it to learn the valid ID range of each table.

## Facts

| Property | Value |
|---|---|
| Rows at scale factor 1 | 32 |
| Scaling | fixed (does not change with scale factor) |
| Volume tier | Tiny |
| Estimated average record | 90 bytes (field-by-field estimate: 100 bytes) |
| Record-size tier | Narrow |
| Estimated data at SF 1 | 0.000 GB |
| Data area | `PB_Ref_Data` (RPB 64, BPC 8) |
| Index area | `PB_Ref_Idx` (BPC 8) |
| Sequence | `SeqBenchmarkTableInfoId` (INT64, starts at 1, increment 1, no cycle) |

## Fields

13 fields. *(std)* marks the standard fields present on every table.

| # | Name | Type | Format | Decimals | Mandatory | Initial | Label | Description | Generation |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `BenchmarkTableInfoId` *(std)* | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Benchmark Table Info Id | Dense sequential identifier, 1..N with no gaps after the initial load. Runtime inserts use NEXT-VALUE(SeqBenchmarkTableInfoId). | Assigned 1..N in load order |
| 2 | `RandomInt10` *(std)* | INTEGER | `>9` |  | Y | `0` | Random Int 10 | Independent uniform random value 1–10 for selecting ≈ 10% subsets. 0 = unassigned (invalid). | Independent uniform 1–10; 0 = unassigned (invalid) |
| 3 | `RandomInt100` *(std)* | INTEGER | `>>9` |  | Y | `0` | Random Int 100 | Independent uniform random value 1–100 for selecting ≈ 1% subsets. 0 = unassigned (invalid). | Independent uniform 1–100; 0 = unassigned (invalid) |
| 4 | `RandomInt1000` *(std)* | INTEGER | `>>>9` |  | Y | `0` | Random Int 1000 | Independent uniform random value 1–1000 for selecting ≈ 0.1% subsets. 0 = unassigned (invalid). | Independent uniform 1–1000; 0 = unassigned (invalid) |
| 5 | `CreatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Created At | When the row was created. For historical rows, a synthetic timestamp consistent with the row's business date. | Consistent with the row's business date; NOW for runtime inserts |
| 6 | `TableName` | CHARACTER | `x(32)` |  | Y | `""` | Table Name | Exact table name | Exact table name |
| 7 | `TableRowCount` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Table Row Count | Rows after the load (named to avoid the reserved/function word ROWCOUNT) | Rows after the load (named to avoid the reserved/function word ROWCOUNT) |
| 8 | `MaxId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Max Id | Highest &lt;Table>Id; equals TableRowCount right after the load | Highest &lt;Table>Id; equals TableRowCount right after the load |
| 9 | `ScaleFactor` | DECIMAL | `>>9.99` | 2 | Y | `1` | Scale Factor | Scale factor used for the load | Scale factor used for the load |
| 10 | `VolumeTier` | CHARACTER | `x(10)` |  | Y | `""` | Volume Tier | Tier at scale factor 1 | Tier at scale factor 1 |
| 11 | `RecordSizeTier` | CHARACTER | `x(10)` |  | Y | `""` | Record Size Tier | Record-size tier of the table | default (data-model §1.5) |
| 12 | `AsOfDate` | DATE | `99/99/9999` |  | Y | `?` (unknown) | As Of Date | End of the history window | End of the history window |
| 13 | `LoadedAt` | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `?` (unknown) | Loaded At | When the load finished | default (data-model §1.5) |

## Indexes

5 indexes (1 table-specific).

| Name | Components | Primary | Unique | Word | Purpose |
|---|---|---|---|---|---|
| `PkBenchmarkTableInfo` *(std)* | BenchmarkTableInfoId ASC | Y | Y | N | Single-row random access by sequential ID; default scan order |
| `IxRandomInt10` *(std)* | RandomInt10 ASC, BenchmarkTableInfoId ASC | N | N | N | Select ≈ 10% of rows (RandomInt10 = k) |
| `IxRandomInt100` *(std)* | RandomInt100 ASC, BenchmarkTableInfoId ASC | N | N | N | Select ≈ 1% of rows (RandomInt100 = k) |
| `IxRandomInt1000` *(std)* | RandomInt1000 ASC, BenchmarkTableInfoId ASC | N | N | N | Select ≈ 0.1% of rows (RandomInt1000 = k) |
| `UxTableName` | TableName ASC | N | Y | N | FIND BenchmarkTableInfo WHERE TableName = "Customer" |

## Relationships

**Parents**

- none

**Children**

- none

## Access examples

ABL: about 1% of rows, then one random existing row.

```abl
FOR EACH BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.RandomInt100 = 42 USE-INDEX IxRandomInt100:
    /* work */
END.

DEFINE VARIABLE r AS INT64 NO-UNDO.
FIND BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.TableName = "BenchmarkTableInfo".
r = RANDOM(1, INTEGER(BenchmarkTableInfo.MaxId)).
FIND BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.BenchmarkTableInfoId = r NO-ERROR.   /* not AVAILABLE => draw again */
```

SQL:

```sql
SELECT * FROM PUB.BenchmarkTableInfo WHERE RandomInt100 = 42;
SELECT MaxId FROM PUB.BenchmarkTableInfo WHERE TableName = 'BenchmarkTableInfo';
SELECT * FROM PUB.BenchmarkTableInfo WHERE BenchmarkTableInfoId = ?;   -- ? drawn uniformly from 1..MaxId
```
