# CustomerNote

`Class T (Transactional)` · `Medium` · `LOB-bearing` · `LOB: CLOB`

[← Schema overview](../README.md)

## Description

Free-text notes and support interactions.

## Facts

| Property | Value |
|---|---|
| Rows at scale factor 1 | 1,500,000 |
| Scaling | linear (rows × scale factor) |
| Volume tier | Medium |
| Estimated average record | 380 bytes (field-by-field estimate: 236 bytes) |
| Record-size tier | LOB-bearing |
| Estimated data at SF 1 | 0.570 GB |
| Estimated LOB content at SF 1 | 1.080 GB |
| Data area | `PB_Master_Std` (RPB 16, BPC 64) |
| Index area | `PB_Master_Idx` (BPC 64) |
| LOB areas | `PB_Lob_Text` (BPC 512) |
| Sequence | `SeqCustomerNoteId` (INT64, starts at 1, increment 1, no cycle) |

## Fields

13 fields. *(std)* marks the standard fields present on every table.

| # | Name | Type | Format | Decimals | Mandatory | Initial | Label | Description | Generation |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `CustomerNoteId` *(std)* | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Customer Note Id | Dense sequential identifier, 1..N with no gaps after the initial load. Runtime inserts use NEXT-VALUE(SeqCustomerNoteId). | Assigned 1..N in load order |
| 2 | `RandomInt10` *(std)* | INTEGER | `>9` |  | Y | `0` | Random Int 10 | Independent uniform random value 1–10 for selecting ≈ 10% subsets. 0 = unassigned (invalid). | Independent uniform 1–10; 0 = unassigned (invalid) |
| 3 | `RandomInt100` *(std)* | INTEGER | `>>9` |  | Y | `0` | Random Int 100 | Independent uniform random value 1–100 for selecting ≈ 1% subsets. 0 = unassigned (invalid). | Independent uniform 1–100; 0 = unassigned (invalid) |
| 4 | `RandomInt1000` *(std)* | INTEGER | `>>>9` |  | Y | `0` | Random Int 1000 | Independent uniform random value 1–1000 for selecting ≈ 0.1% subsets. 0 = unassigned (invalid). | Independent uniform 1–1000; 0 = unassigned (invalid) |
| 5 | `CreatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Created At | When the row was created. For historical rows, a synthetic timestamp consistent with the row's business date. | Consistent with the row's business date; NOW for runtime inserts |
| 6 | `CustomerId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Customer Id | Reference to [Customer](Customer.md).`CustomerId` | Zipf-skewed (a few customers have many notes) |
| 7 | `EmployeeId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Employee Id | Reference to [Employee](Employee.md).`EmployeeId` | Random existing parent row, respecting the cardinality |
| 8 | `NoteKind` | CHARACTER | `x(10)` |  | Y | `""` | Note Kind | Kind of note | CALL, EMAIL, BRANCH, COMPLAINT, SYSTEM |
| 9 | `NoteDateTime` | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `?` (unknown) | Note Date Time | When the note was written | Within the last 5 years |
| 10 | `Summary` | CHARACTER | `x(300)` |  | Y | `""` | Summary | 80–300 characters of generated banking vocabulary (word-indexed) | 80–300 characters of generated banking vocabulary (word-indexed) |
| 11 | `NoteText` | CLOB | – |  | N | `?` (unknown) | Note Text | Present on 60%; 200 B–8 KB (avg 1.2 KB). Area PB_Lob_Text | Present on 60%; 200 B–8 KB (avg 1.2 KB). Area PB_Lob_Text |
| 12 | `FollowUpDate` | DATE | `99/99/9999` |  | N | `?` (unknown) | Follow Up Date | Follow-up date | 15% set |
| 13 | `IsResolved` | LOGICAL | `yes/no` |  | Y | `no` | Is Resolved | Whether the note is resolved | 85% yes |

## LOB fields

| Field | Type | Area | Max size | Codepage | Content | Populated | Min / Avg / Max bytes |
|---|---|---|---|---|---|---|---|
| `NoteText` | CLOB | `PB_Lob_Text` | 8K | UTF-8 | free text | 60% | 200 / 1,200 / 8,192 |

## Indexes

7 indexes (3 table-specific).

| Name | Components | Primary | Unique | Word | Purpose |
|---|---|---|---|---|---|
| `PkCustomerNote` *(std)* | CustomerNoteId ASC | Y | Y | N | Single-row random access by sequential ID; default scan order |
| `IxRandomInt10` *(std)* | RandomInt10 ASC, CustomerNoteId ASC | N | N | N | Select ≈ 10% of rows (RandomInt10 = k) |
| `IxRandomInt100` *(std)* | RandomInt100 ASC, CustomerNoteId ASC | N | N | N | Select ≈ 1% of rows (RandomInt100 = k) |
| `IxRandomInt1000` *(std)* | RandomInt1000 ASC, CustomerNoteId ASC | N | N | N | Select ≈ 0.1% of rows (RandomInt1000 = k) |
| `IxCustomerDate` | CustomerId ASC, NoteDateTime DESC | N | N | N | Newest notes first |
| `IxEmployeeDate` | EmployeeId ASC, NoteDateTime ASC | N | N | N | Employee activity |
| `WxSummary` | Summary ASC | N | N | Y | Full-text search |

## Relationships

**Parents**

- `CustomerId` → [Customer](Customer.md).`CustomerId` — 1.5 / 0–20 (Zipf) children per parent
- `EmployeeId` → [Employee](Employee.md).`EmployeeId` — 300 / 0–2,000 children per parent

**Children**

- none

## Access examples

ABL: about 1% of rows, then one random existing row.

```abl
FOR EACH CustomerNote NO-LOCK WHERE CustomerNote.RandomInt100 = 42 USE-INDEX IxRandomInt100:
    /* work */
END.

DEFINE VARIABLE r AS INT64 NO-UNDO.
FIND BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.TableName = "CustomerNote".
r = RANDOM(1, INTEGER(BenchmarkTableInfo.MaxId)).
FIND CustomerNote NO-LOCK WHERE CustomerNote.CustomerNoteId = r NO-ERROR.   /* not AVAILABLE => draw again */
```

SQL:

```sql
SELECT * FROM PUB.CustomerNote WHERE RandomInt100 = 42;
SELECT MaxId FROM PUB.BenchmarkTableInfo WHERE TableName = 'CustomerNote';
SELECT * FROM PUB.CustomerNote WHERE CustomerNoteId = ?;   -- ? drawn uniformly from 1..MaxId
```
