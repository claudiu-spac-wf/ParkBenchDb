# LoginEvent

`Class T (Transactional)` · `Large` · `Narrow` · `LOB: none`

[← Schema overview](../README.md)

## Description

Online banking login/session events.

## Facts

| Property | Value |
|---|---|
| Rows at scale factor 1 | 12,000,000 |
| Scaling | linear (rows × scale factor) |
| Volume tier | Large |
| Estimated average record | 120 bytes (field-by-field estimate: 107 bytes) |
| Record-size tier | Narrow |
| Estimated data at SF 1 | 1.440 GB |
| Data area | `PB_Txn_Large` (RPB 32, BPC 512) |
| Index area | `PB_Txn_Idx` (BPC 512) |
| Sequence | `SeqLoginEventId` (INT64, starts at 1, increment 1, no cycle) |

## Fields

13 fields. *(std)* marks the standard fields present on every table.

| # | Name | Type | Format | Decimals | Mandatory | Initial | Label | Description | Generation |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `LoginEventId` *(std)* | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Login Event Id | Dense sequential identifier, 1..N with no gaps after the initial load. Runtime inserts use NEXT-VALUE(SeqLoginEventId). | Assigned 1..N in load order |
| 2 | `RandomInt10` *(std)* | INTEGER | `>9` |  | Y | `0` | Random Int 10 | Independent uniform random value 1–10 for selecting ≈ 10% subsets. 0 = unassigned (invalid). | Independent uniform 1–10; 0 = unassigned (invalid) |
| 3 | `RandomInt100` *(std)* | INTEGER | `>>9` |  | Y | `0` | Random Int 100 | Independent uniform random value 1–100 for selecting ≈ 1% subsets. 0 = unassigned (invalid). | Independent uniform 1–100; 0 = unassigned (invalid) |
| 4 | `RandomInt1000` *(std)* | INTEGER | `>>>9` |  | Y | `0` | Random Int 1000 | Independent uniform random value 1–1000 for selecting ≈ 0.1% subsets. 0 = unassigned (invalid). | Independent uniform 1–1000; 0 = unassigned (invalid) |
| 5 | `CreatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Created At | When the row was created. For historical rows, a synthetic timestamp consistent with the row's business date. | Consistent with the row's business date; NOW for runtime inserts |
| 6 | `CustomerId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Customer Id | Reference to [Customer](Customer.md).`CustomerId` | skewed (30% of customers never log in) |
| 7 | `EventDateTime` | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `?` (unknown) | Event Date Time | When the event occurred | default (data-model §1.5) |
| 8 | `EventKind` | CHARACTER | `x(8)` |  | Y | `LOGIN` | Event Kind | LOGIN 70%, FAILED 8%, MFA 12%, LOGOUT 10% | LOGIN 70%, FAILED 8%, MFA 12%, LOGOUT 10% |
| 9 | `Channel` | CHARACTER | `x(6)` |  | Y | `WEB` | Channel | WEB, MOBILE | WEB, MOBILE |
| 10 | `IpAddress` | CHARACTER | `x(39)` |  | Y | `""` | Ip Address | Client IP address | IPv4 90%, IPv6 10% |
| 11 | `DeviceId` | CHARACTER | `x(32)` |  | Y | `""` | Device Id | Client device identifier | default (data-model §1.5) |
| 12 | `IsSuccess` | LOGICAL | `yes/no` |  | Y | `yes` | Is Success | Whether the event succeeded | default (data-model §1.5) |
| 13 | `SessionSeconds` | INTEGER | `>>>>>9` |  | Y | `0` | Session Seconds | Session length in seconds | default (data-model §1.5) |

## Indexes

5 indexes (1 table-specific).

| Name | Components | Primary | Unique | Word | Purpose |
|---|---|---|---|---|---|
| `PkLoginEvent` *(std)* | LoginEventId ASC | Y | Y | N | Single-row random access by sequential ID; default scan order |
| `IxRandomInt10` *(std)* | RandomInt10 ASC, LoginEventId ASC | N | N | N | Select ≈ 10% of rows (RandomInt10 = k) |
| `IxRandomInt100` *(std)* | RandomInt100 ASC, LoginEventId ASC | N | N | N | Select ≈ 1% of rows (RandomInt100 = k) |
| `IxRandomInt1000` *(std)* | RandomInt1000 ASC, LoginEventId ASC | N | N | N | Select ≈ 0.1% of rows (RandomInt1000 = k) |
| `IxCustomerTime` | CustomerId ASC, EventDateTime DESC | N | N | N | Recent logins for a customer |

## Relationships

**Parents**

- `CustomerId` → [Customer](Customer.md).`CustomerId` — 12 / 0–400 (skewed) children per parent

**Children**

- none

## Access examples

ABL: about 1% of rows, then one random existing row.

```abl
FOR EACH LoginEvent NO-LOCK WHERE LoginEvent.RandomInt100 = 42 USE-INDEX IxRandomInt100:
    /* work */
END.

DEFINE VARIABLE r AS INT64 NO-UNDO.
FIND BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.TableName = "LoginEvent".
r = RANDOM(1, INTEGER(BenchmarkTableInfo.MaxId)).
FIND LoginEvent NO-LOCK WHERE LoginEvent.LoginEventId = r NO-ERROR.   /* not AVAILABLE => draw again */
```

SQL:

```sql
SELECT * FROM PUB.LoginEvent WHERE RandomInt100 = 42;
SELECT MaxId FROM PUB.BenchmarkTableInfo WHERE TableName = 'LoginEvent';
SELECT * FROM PUB.LoginEvent WHERE LoginEventId = ?;   -- ? drawn uniformly from 1..MaxId
```
