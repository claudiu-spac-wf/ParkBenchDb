# AccountHolder

`Class M (Master)` · `Medium` · `Narrow` · `LOB: none`

[← Schema overview](../README.md)

## Description

Customer-to-account ownership with role (primary, joint, authorized).

## Facts

| Property | Value |
|---|---|
| Rows at scale factor 1 | 2,000,000 |
| Scaling | linear (rows × scale factor) |
| Volume tier | Medium |
| Estimated average record | 70 bytes (field-by-field estimate: 77 bytes) |
| Record-size tier | Narrow |
| Estimated data at SF 1 | 0.140 GB |
| Data area | `PB_Master_Narrow` (RPB 32, BPC 64) |
| Index area | `PB_Master_Idx` (BPC 64) |
| Sequence | `SeqAccountHolderId` (INT64, starts at 1, increment 1, no cycle) |

## Fields

11 fields. *(std)* marks the standard fields present on every table.

| # | Name | Type | Format | Decimals | Mandatory | Initial | Label | Description | Generation |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `AccountHolderId` *(std)* | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Account Holder Id | Dense sequential identifier, 1..N with no gaps after the initial load. Runtime inserts use NEXT-VALUE(SeqAccountHolderId). | Assigned 1..N in load order |
| 2 | `RandomInt10` *(std)* | INTEGER | `>9` |  | Y | `0` | Random Int 10 | Independent uniform random value 1–10 for selecting ≈ 10% subsets. 0 = unassigned (invalid). | Independent uniform 1–10; 0 = unassigned (invalid) |
| 3 | `RandomInt100` *(std)* | INTEGER | `>>9` |  | Y | `0` | Random Int 100 | Independent uniform random value 1–100 for selecting ≈ 1% subsets. 0 = unassigned (invalid). | Independent uniform 1–100; 0 = unassigned (invalid) |
| 4 | `RandomInt1000` *(std)* | INTEGER | `>>>9` |  | Y | `0` | Random Int 1000 | Independent uniform random value 1–1000 for selecting ≈ 0.1% subsets. 0 = unassigned (invalid). | Independent uniform 1–1000; 0 = unassigned (invalid) |
| 5 | `CreatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Created At | When the row was created. For historical rows, a synthetic timestamp consistent with the row's business date. | Consistent with the row's business date; NOW for runtime inserts |
| 6 | `AccountId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Account Id | Reference to [Account](Account.md).`AccountId` | Random existing parent row, respecting the cardinality |
| 7 | `CustomerId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Customer Id | Reference to [Customer](Customer.md).`CustomerId` | Random existing parent row, respecting the cardinality |
| 8 | `HolderRole` | CHARACTER | `x(10)` |  | Y | `PRIMARY` | Holder Role | Role of the holder on the account | PRIMARY (exactly one per account), JOINT, AUTHORIZED, TRUSTEE |
| 9 | `OwnershipPercent` | DECIMAL | `>>9.99` | 2 | Y | `0` | Ownership Percent | Ownership share (%) | The account's holders sum to 100 |
| 10 | `AddedDate` | DATE | `99/99/9999` |  | Y | `?` (unknown) | Added Date | Date the holder was added to the account | default (data-model §1.5) |
| 11 | `UpdatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Updated At | Last modification time; equals CreatedAt right after the load. | Equal to CreatedAt at load |

## Indexes

6 indexes (2 table-specific).

| Name | Components | Primary | Unique | Word | Purpose |
|---|---|---|---|---|---|
| `PkAccountHolder` *(std)* | AccountHolderId ASC | Y | Y | N | Single-row random access by sequential ID; default scan order |
| `IxRandomInt10` *(std)* | RandomInt10 ASC, AccountHolderId ASC | N | N | N | Select ≈ 10% of rows (RandomInt10 = k) |
| `IxRandomInt100` *(std)* | RandomInt100 ASC, AccountHolderId ASC | N | N | N | Select ≈ 1% of rows (RandomInt100 = k) |
| `IxRandomInt1000` *(std)* | RandomInt1000 ASC, AccountHolderId ASC | N | N | N | Select ≈ 0.1% of rows (RandomInt1000 = k) |
| `UxAccountCustomer` | AccountId ASC, CustomerId ASC | N | Y | N | Holders of an account |
| `IxCustomerAccount` | CustomerId ASC, AccountId ASC | N | N | N | Accounts of a customer |

## Relationships

**Parents**

- `AccountId` → [Account](Account.md).`AccountId` — 1.33 / 1–4 children per parent
- `CustomerId` → [Customer](Customer.md).`CustomerId` — 2.0 / 1–8 children per parent

**Children**

- none

## Access examples

ABL: about 1% of rows, then one random existing row.

```abl
FOR EACH AccountHolder NO-LOCK WHERE AccountHolder.RandomInt100 = 42 USE-INDEX IxRandomInt100:
    /* work */
END.

DEFINE VARIABLE r AS INT64 NO-UNDO.
FIND BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.TableName = "AccountHolder".
r = RANDOM(1, INTEGER(BenchmarkTableInfo.MaxId)).
FIND AccountHolder NO-LOCK WHERE AccountHolder.AccountHolderId = r NO-ERROR.   /* not AVAILABLE => draw again */
```

SQL:

```sql
SELECT * FROM PUB.AccountHolder WHERE RandomInt100 = 42;
SELECT MaxId FROM PUB.BenchmarkTableInfo WHERE TableName = 'AccountHolder';
SELECT * FROM PUB.AccountHolder WHERE AccountHolderId = ?;   -- ? drawn uniformly from 1..MaxId
```
