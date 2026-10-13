# AuditLog

`Class T (Transactional)` · `Very Large` · `Narrow` · `LOB: none`

[← Schema overview](../README.md)

## Description

System change log.

Append-only. It has only the four standard indexes, making it the insert-throughput reference table.

## Facts

| Property | Value |
|---|---|
| Rows at scale factor 1 | 50,000,000 |
| Scaling | linear (rows × scale factor) |
| Volume tier | Very Large |
| Estimated average record | 110 bytes (field-by-field estimate: 112 bytes) |
| Record-size tier | Narrow |
| Estimated data at SF 1 | 5.500 GB |
| Data area | `PB_Txn_Audit` (RPB 32, BPC 512) |
| Index area | `PB_Txn_Idx` (BPC 512) |
| Sequence | `SeqAuditLogId` (INT64, starts at 1, increment 1, no cycle) |

## Fields

11 fields. *(std)* marks the standard fields present on every table.

| # | Name | Type | Format | Decimals | Mandatory | Initial | Label | Description | Generation |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `AuditLogId` *(std)* | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Audit Log Id | Dense sequential identifier, 1..N with no gaps after the initial load. Runtime inserts use NEXT-VALUE(SeqAuditLogId). | Assigned 1..N in load order |
| 2 | `RandomInt10` *(std)* | INTEGER | `>9` |  | Y | `0` | Random Int 10 | Independent uniform random value 1–10 for selecting ≈ 10% subsets. 0 = unassigned (invalid). | Independent uniform 1–10; 0 = unassigned (invalid) |
| 3 | `RandomInt100` *(std)* | INTEGER | `>>9` |  | Y | `0` | Random Int 100 | Independent uniform random value 1–100 for selecting ≈ 1% subsets. 0 = unassigned (invalid). | Independent uniform 1–100; 0 = unassigned (invalid) |
| 4 | `RandomInt1000` *(std)* | INTEGER | `>>>9` |  | Y | `0` | Random Int 1000 | Independent uniform random value 1–1000 for selecting ≈ 0.1% subsets. 0 = unassigned (invalid). | Independent uniform 1–1000; 0 = unassigned (invalid) |
| 5 | `CreatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Created At | When the row was created. For historical rows, a synthetic timestamp consistent with the row's business date. | Consistent with the row's business date; NOW for runtime inserts |
| 6 | `EventDateTime` | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `?` (unknown) | Event Date Time | When the event occurred | Monotonically increasing with AuditLogId |
| 7 | `TableName` | CHARACTER | `x(32)` |  | Y | `""` | Table Name | Name of the audited table (weighted toward Account, Customer, Card) | Name of the audited table (weighted toward Account, Customer, Card) |
| 8 | `RecordId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Record Id | &lt;Table>Id of the audited row | &lt;Table>Id of the audited row |
| 9 | `AuditAction` | CHARACTER | `x(1)` |  | Y | `U` | Audit Action | C 20%, U 75%, D 5% (named to avoid the SQL reserved word ACTION) | C 20%, U 75%, D 5% (named to avoid the SQL reserved word ACTION) |
| 10 | `EmployeeId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Employee Id | Reference to [Employee](Employee.md).`EmployeeId` | 0 = system (70%) |
| 11 | `ChangeSummary` | CHARACTER | `x(60)` |  | Y | `""` | Change Summary | e.g. Status: OPEN->DORMANT | e.g. Status: OPEN->DORMANT |

## Indexes

4 indexes (0 table-specific).

| Name | Components | Primary | Unique | Word | Purpose |
|---|---|---|---|---|---|
| `PkAuditLog` *(std)* | AuditLogId ASC | Y | Y | N | Single-row random access by sequential ID; default scan order |
| `IxRandomInt10` *(std)* | RandomInt10 ASC, AuditLogId ASC | N | N | N | Select ≈ 10% of rows (RandomInt10 = k) |
| `IxRandomInt100` *(std)* | RandomInt100 ASC, AuditLogId ASC | N | N | N | Select ≈ 1% of rows (RandomInt100 = k) |
| `IxRandomInt1000` *(std)* | RandomInt1000 ASC, AuditLogId ASC | N | N | N | Select ≈ 0.1% of rows (RandomInt1000 = k) |

## Relationships

**Parents**

- `EmployeeId` → [Employee](Employee.md).`EmployeeId` — 3,000 / 0–20,000 children per parent; optional (0 = none); not indexed: Minimal-index table by design (FR-020)

**Children**

- none

## Access examples

ABL: about 1% of rows, then one random existing row.

```abl
FOR EACH AuditLog NO-LOCK WHERE AuditLog.RandomInt100 = 42 USE-INDEX IxRandomInt100:
    /* work */
END.

DEFINE VARIABLE r AS INT64 NO-UNDO.
FIND BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.TableName = "AuditLog".
r = RANDOM(1, INTEGER(BenchmarkTableInfo.MaxId)).
FIND AuditLog NO-LOCK WHERE AuditLog.AuditLogId = r NO-ERROR.   /* not AVAILABLE => draw again */
```

SQL:

```sql
SELECT * FROM PUB.AuditLog WHERE RandomInt100 = 42;
SELECT MaxId FROM PUB.BenchmarkTableInfo WHERE TableName = 'AuditLog';
SELECT * FROM PUB.AuditLog WHERE AuditLogId = ?;   -- ? drawn uniformly from 1..MaxId
```
