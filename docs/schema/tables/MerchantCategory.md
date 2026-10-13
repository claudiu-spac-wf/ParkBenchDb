# MerchantCategory

`Class R (Reference)` · `Tiny` · `Narrow` · `LOB: none`

[← Schema overview](../README.md)

## Description

Merchant category codes.

## Facts

| Property | Value |
|---|---|
| Rows at scale factor 1 | 600 |
| Scaling | fixed (does not change with scale factor) |
| Volume tier | Tiny |
| Estimated average record | 110 bytes (field-by-field estimate: 100 bytes) |
| Record-size tier | Narrow |
| Estimated data at SF 1 | 0.000 GB |
| Data area | `PB_Ref_Data` (RPB 64, BPC 8) |
| Index area | `PB_Ref_Idx` (BPC 8) |
| Sequence | `SeqMerchantCategoryId` (INT64, starts at 1, increment 1, no cycle) |

## Fields

8 fields. *(std)* marks the standard fields present on every table.

| # | Name | Type | Format | Decimals | Mandatory | Initial | Label | Description | Generation |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `MerchantCategoryId` *(std)* | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Merchant Category Id | Dense sequential identifier, 1..N with no gaps after the initial load. Runtime inserts use NEXT-VALUE(SeqMerchantCategoryId). | Assigned 1..N in load order |
| 2 | `RandomInt10` *(std)* | INTEGER | `>9` |  | Y | `0` | Random Int 10 | Independent uniform random value 1–10 for selecting ≈ 10% subsets. 0 = unassigned (invalid). | Independent uniform 1–10; 0 = unassigned (invalid) |
| 3 | `RandomInt100` *(std)* | INTEGER | `>>9` |  | Y | `0` | Random Int 100 | Independent uniform random value 1–100 for selecting ≈ 1% subsets. 0 = unassigned (invalid). | Independent uniform 1–100; 0 = unassigned (invalid) |
| 4 | `RandomInt1000` *(std)* | INTEGER | `>>>9` |  | Y | `0` | Random Int 1000 | Independent uniform random value 1–1000 for selecting ≈ 0.1% subsets. 0 = unassigned (invalid). | Independent uniform 1–1000; 0 = unassigned (invalid) |
| 5 | `CreatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Created At | When the row was created. For historical rows, a synthetic timestamp consistent with the row's business date. | Consistent with the row's business date; NOW for runtime inserts |
| 6 | `MccCode` | CHARACTER | `x(4)` |  | Y | `""` | Mcc Code | Merchant category code | 4-digit merchant category code |
| 7 | `Description` | CHARACTER | `x(80)` |  | Y | `""` | Description | Human-readable description | default (data-model §1.5) |
| 8 | `CategoryGroup` | CHARACTER | `x(30)` |  | Y | `""` | Category Group | Merchant category group | ~20 groups (Grocery, Travel, Fuel…) |

## Indexes

5 indexes (1 table-specific).

| Name | Components | Primary | Unique | Word | Purpose |
|---|---|---|---|---|---|
| `PkMerchantCategory` *(std)* | MerchantCategoryId ASC | Y | Y | N | Single-row random access by sequential ID; default scan order |
| `IxRandomInt10` *(std)* | RandomInt10 ASC, MerchantCategoryId ASC | N | N | N | Select ≈ 10% of rows (RandomInt10 = k) |
| `IxRandomInt100` *(std)* | RandomInt100 ASC, MerchantCategoryId ASC | N | N | N | Select ≈ 1% of rows (RandomInt100 = k) |
| `IxRandomInt1000` *(std)* | RandomInt1000 ASC, MerchantCategoryId ASC | N | N | N | Select ≈ 0.1% of rows (RandomInt1000 = k) |
| `UxMccCode` | MccCode ASC | N | Y | N | Lookup |

## Relationships

**Parents**

- none

**Children**

- [Merchant](Merchant.md).`MerchantCategoryId`

## Access examples

ABL: about 1% of rows, then one random existing row.

```abl
FOR EACH MerchantCategory NO-LOCK WHERE MerchantCategory.RandomInt100 = 42 USE-INDEX IxRandomInt100:
    /* work */
END.

DEFINE VARIABLE r AS INT64 NO-UNDO.
FIND BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.TableName = "MerchantCategory".
r = RANDOM(1, INTEGER(BenchmarkTableInfo.MaxId)).
FIND MerchantCategory NO-LOCK WHERE MerchantCategory.MerchantCategoryId = r NO-ERROR.   /* not AVAILABLE => draw again */
```

SQL:

```sql
SELECT * FROM PUB.MerchantCategory WHERE RandomInt100 = 42;
SELECT MaxId FROM PUB.BenchmarkTableInfo WHERE TableName = 'MerchantCategory';
SELECT * FROM PUB.MerchantCategory WHERE MerchantCategoryId = ?;   -- ? drawn uniformly from 1..MaxId
```
