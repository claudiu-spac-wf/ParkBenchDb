# Employee

`Class M (Master)` · `Small` · `LOB-bearing` · `LOB: BLOB`

[← Schema overview](../README.md)

## Description

Bank staff.

## Facts

| Property | Value |
|---|---|
| Rows at scale factor 1 | 5,000 |
| Scaling | linear (rows × scale factor) |
| Volume tier | Small |
| Estimated average record | 330 bytes (field-by-field estimate: 191 bytes) |
| Record-size tier | LOB-bearing |
| Estimated data at SF 1 | 0.002 GB |
| Estimated LOB content at SF 1 | 0.098 GB |
| Data area | `PB_Ref_Data` (RPB 64, BPC 8) |
| Index area | `PB_Ref_Idx` (BPC 8) |
| LOB areas | `PB_Lob_Doc` (BPC 512) |
| Sequence | `SeqEmployeeId` (INT64, starts at 1, increment 1, no cycle) |

## Fields

17 fields. *(std)* marks the standard fields present on every table.

| # | Name | Type | Format | Decimals | Mandatory | Initial | Label | Description | Generation |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `EmployeeId` *(std)* | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Employee Id | Dense sequential identifier, 1..N with no gaps after the initial load. Runtime inserts use NEXT-VALUE(SeqEmployeeId). | Assigned 1..N in load order |
| 2 | `RandomInt10` *(std)* | INTEGER | `>9` |  | Y | `0` | Random Int 10 | Independent uniform random value 1–10 for selecting ≈ 10% subsets. 0 = unassigned (invalid). | Independent uniform 1–10; 0 = unassigned (invalid) |
| 3 | `RandomInt100` *(std)* | INTEGER | `>>9` |  | Y | `0` | Random Int 100 | Independent uniform random value 1–100 for selecting ≈ 1% subsets. 0 = unassigned (invalid). | Independent uniform 1–100; 0 = unassigned (invalid) |
| 4 | `RandomInt1000` *(std)* | INTEGER | `>>>9` |  | Y | `0` | Random Int 1000 | Independent uniform random value 1–1000 for selecting ≈ 0.1% subsets. 0 = unassigned (invalid). | Independent uniform 1–1000; 0 = unassigned (invalid) |
| 5 | `CreatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Created At | When the row was created. For historical rows, a synthetic timestamp consistent with the row's business date. | Consistent with the row's business date; NOW for runtime inserts |
| 6 | `EmployeeNumber` | CHARACTER | `x(10)` |  | Y | `""` | Employee Number | Employee business key | E + 7 digits |
| 7 | `BranchId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Branch Id | Reference to [Branch](Branch.md).`BranchId` | 15% at the head-office branch (BranchId 1) |
| 8 | `FirstName` | CHARACTER | `x(30)` |  | Y | `""` | First Name | Given name | default (data-model §1.5) |
| 9 | `LastName` | CHARACTER | `x(40)` |  | Y | `""` | Last Name | Family name | default (data-model §1.5) |
| 10 | `JobTitle` | CHARACTER | `x(40)` |  | Y | `""` | Job Title | Job title | Teller, Banker, Loan Officer, Manager, Analyst… |
| 11 | `Email` | CHARACTER | `x(80)` |  | Y | `""` | Email | Email address | default (data-model §1.5) |
| 12 | `HireDate` | DATE | `99/99/9999` |  | Y | `?` (unknown) | Hire Date | Date the employee was hired | default (data-model §1.5) |
| 13 | `TerminationDate` | DATE | `99/99/9999` |  | N | `?` (unknown) | Termination Date | Date employment ended | Set for 8% of rows |
| 14 | `IsBranchManager` | LOGICAL | `yes/no` |  | Y | `no` | Is Branch Manager | Whether the employee manages their branch | Exactly one yes per branch |
| 15 | `Salary` | DECIMAL | `->>>,>>>,>>>,>>9.99` | 2 | Y | `0` | Salary | Annual salary | 35,000–250,000 |
| 16 | `Photo` | BLOB | – |  | N | `?` (unknown) | Photo | JPEG, 8–48 KB (avg 24 KB); present on 80% of rows. Area PB_Lob_Doc | JPEG, 8–48 KB (avg 24 KB); present on 80% of rows. Area PB_Lob_Doc |
| 17 | `UpdatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Updated At | Last modification time; equals CreatedAt right after the load. | Equal to CreatedAt at load |

## LOB fields

| Field | Type | Area | Max size | Codepage | Content | Populated | Min / Avg / Max bytes |
|---|---|---|---|---|---|---|---|
| `Photo` | BLOB | `PB_Lob_Doc` | 64K | – | JPEG | 80% | 8,192 / 24,576 / 49,152 |

## Indexes

7 indexes (3 table-specific).

| Name | Components | Primary | Unique | Word | Purpose |
|---|---|---|---|---|---|
| `PkEmployee` *(std)* | EmployeeId ASC | Y | Y | N | Single-row random access by sequential ID; default scan order |
| `IxRandomInt10` *(std)* | RandomInt10 ASC, EmployeeId ASC | N | N | N | Select ≈ 10% of rows (RandomInt10 = k) |
| `IxRandomInt100` *(std)* | RandomInt100 ASC, EmployeeId ASC | N | N | N | Select ≈ 1% of rows (RandomInt100 = k) |
| `IxRandomInt1000` *(std)* | RandomInt1000 ASC, EmployeeId ASC | N | N | N | Select ≈ 0.1% of rows (RandomInt1000 = k) |
| `UxEmployeeNumber` | EmployeeNumber ASC | N | Y | N | Lookup |
| `IxBranch` | BranchId ASC, LastName ASC | N | N | N | Staff per branch |
| `IxName` | LastName ASC, FirstName ASC | N | N | N | Name search |

## Relationships

**Parents**

- `BranchId` → [Branch](Branch.md).`BranchId` — 20 / 5–750 (head office ≈ 750) children per parent

**Children**

- [InterestRateHistory](InterestRateHistory.md).`ChangedByEmployeeId`
- [CustomerDocument](CustomerDocument.md).`VerifiedByEmployeeId`
- [CustomerNote](CustomerNote.md).`EmployeeId`
- [Loan](Loan.md).`LoanOfficerEmployeeId`
- [AuditLog](AuditLog.md).`EmployeeId`

## Access examples

ABL: about 1% of rows, then one random existing row.

```abl
FOR EACH Employee NO-LOCK WHERE Employee.RandomInt100 = 42 USE-INDEX IxRandomInt100:
    /* work */
END.

DEFINE VARIABLE r AS INT64 NO-UNDO.
FIND BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.TableName = "Employee".
r = RANDOM(1, INTEGER(BenchmarkTableInfo.MaxId)).
FIND Employee NO-LOCK WHERE Employee.EmployeeId = r NO-ERROR.   /* not AVAILABLE => draw again */
```

SQL:

```sql
SELECT * FROM PUB.Employee WHERE RandomInt100 = 42;
SELECT MaxId FROM PUB.BenchmarkTableInfo WHERE TableName = 'Employee';
SELECT * FROM PUB.Employee WHERE EmployeeId = ?;   -- ? drawn uniformly from 1..MaxId
```
