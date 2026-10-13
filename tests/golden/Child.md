# Child

`Class T (Transactional)` · `Small` · `LOB-bearing` · `LOB: CLOB`

[← Schema overview](../README.md)

## Description

A child row with a note.

## Facts

| Property | Value |
|---|---|
| Rows at scale factor 1 | 2,000 |
| Scaling | linear (rows × scale factor) |
| Volume tier | Small |
| Estimated average record | 67 bytes (field-by-field estimate: 67 bytes) |
| Record-size tier | LOB-bearing |
| Estimated data at SF 1 | 0.000 GB |
| Estimated LOB content at SF 1 | 0.001 GB |
| Data area | `FxData` (RPB 32, BPC 8) |
| Index area | `FxIdx` (BPC 8) |
| LOB areas | `FxLob` (BPC 8) |
| Sequence | `SeqChildId` (INT64, starts at 1, increment 1, no cycle) |

## Fields

8 fields. *(std)* marks the standard fields present on every table.

| # | Name | Type | Format | Decimals | Mandatory | Initial | Label | Description | Generation |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `ChildId` *(std)* | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Child Id | Dense sequential identifier, 1..N with no gaps after the initial load. Runtime inserts use NEXT-VALUE(SeqChildId). | Assigned 1..N in load order |
| 2 | `RandomInt10` *(std)* | INTEGER | `>9` |  | Y | `0` | Random Int 10 | Independent uniform random value 1–10 for selecting ≈ 10% subsets. 0 = unassigned (invalid). | Independent uniform 1–10; 0 = unassigned (invalid) |
| 3 | `RandomInt100` *(std)* | INTEGER | `>>9` |  | Y | `0` | Random Int 100 | Independent uniform random value 1–100 for selecting ≈ 1% subsets. 0 = unassigned (invalid). | Independent uniform 1–100; 0 = unassigned (invalid) |
| 4 | `RandomInt1000` *(std)* | INTEGER | `>>>9` |  | Y | `0` | Random Int 1000 | Independent uniform random value 1–1000 for selecting ≈ 0.1% subsets. 0 = unassigned (invalid). | Independent uniform 1–1000; 0 = unassigned (invalid) |
| 5 | `CreatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Created At | When the row was created. For historical rows, a synthetic timestamp consistent with the row's business date. | Consistent with the row's business date; NOW for runtime inserts |
| 6 | `ParentId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Parent Id | Reference to [Parent](Parent.md).`ParentId` | Random existing parent row |
| 7 | `PostedAt` | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `?` (unknown) | Posted At | When the child was posted | Uniform over the history window |
| 8 | `NoteText` | CLOB | – |  | N | `?` (unknown) | Note Text | Free-text note | Generated prose |

## LOB fields

| Field | Type | Area | Max size | Codepage | Content | Populated | Min / Avg / Max bytes |
|---|---|---|---|---|---|---|---|
| `NoteText` | CLOB | `FxLob` | 8K | UTF-8 | free text | 50% | 100 / 1,000 / 8,192 |

## Indexes

5 indexes (1 table-specific).

| Name | Components | Primary | Unique | Word | Purpose |
|---|---|---|---|---|---|
| `PkChild` *(std)* | ChildId ASC | Y | Y | N | Single-row random access by sequential ID; default scan order |
| `IxRandomInt10` *(std)* | RandomInt10 ASC, ChildId ASC | N | N | N | Select ≈ 10% of rows (RandomInt10 = k) |
| `IxRandomInt100` *(std)* | RandomInt100 ASC, ChildId ASC | N | N | N | Select ≈ 1% of rows (RandomInt100 = k) |
| `IxRandomInt1000` *(std)* | RandomInt1000 ASC, ChildId ASC | N | N | N | Select ≈ 0.1% of rows (RandomInt1000 = k) |
| `IxParentPosted` | ParentId ASC, PostedAt DESC | N | N | N | A parent's children, newest first |

## Relationships

**Parents**

- `ParentId` → [Parent](Parent.md).`ParentId` — 2 / 0–5 children per parent

**Children**

- none

## Access examples

ABL: about 1% of rows, then one random existing row.

```abl
FOR EACH Child NO-LOCK WHERE Child.RandomInt100 = 42 USE-INDEX IxRandomInt100:
    /* work */
END.

DEFINE VARIABLE r AS INT64 NO-UNDO.
FIND BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.TableName = "Child".
r = RANDOM(1, INTEGER(BenchmarkTableInfo.MaxId)).
FIND Child NO-LOCK WHERE Child.ChildId = r NO-ERROR.   /* not AVAILABLE => draw again */
```

SQL:

```sql
SELECT * FROM PUB.Child WHERE RandomInt100 = 42;
SELECT MaxId FROM PUB.BenchmarkTableInfo WHERE TableName = 'Child';
SELECT * FROM PUB.Child WHERE ChildId = ?;   -- ? drawn uniformly from 1..MaxId
```
