# CustomerAddress

`Class M (Master)` · `Medium` · `Standard` · `LOB: none`

[← Schema overview](../README.md)

## Description

Postal addresses (home, mailing, work).

## Facts

| Property | Value |
|---|---|
| Rows at scale factor 1 | 1,500,000 |
| Scaling | linear (rows × scale factor) |
| Volume tier | Medium |
| Estimated average record | 220 bytes (field-by-field estimate: 178 bytes) |
| Record-size tier | Standard |
| Estimated data at SF 1 | 0.330 GB |
| Data area | `PB_Master_Std` (RPB 16, BPC 64) |
| Index area | `PB_Master_Idx` (BPC 64) |
| Sequence | `SeqCustomerAddressId` (INT64, starts at 1, increment 1, no cycle) |

## Fields

17 fields. *(std)* marks the standard fields present on every table.

| # | Name | Type | Format | Decimals | Mandatory | Initial | Label | Description | Generation |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `CustomerAddressId` *(std)* | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Customer Address Id | Dense sequential identifier, 1..N with no gaps after the initial load. Runtime inserts use NEXT-VALUE(SeqCustomerAddressId). | Assigned 1..N in load order |
| 2 | `RandomInt10` *(std)* | INTEGER | `>9` |  | Y | `0` | Random Int 10 | Independent uniform random value 1–10 for selecting ≈ 10% subsets. 0 = unassigned (invalid). | Independent uniform 1–10; 0 = unassigned (invalid) |
| 3 | `RandomInt100` *(std)* | INTEGER | `>>9` |  | Y | `0` | Random Int 100 | Independent uniform random value 1–100 for selecting ≈ 1% subsets. 0 = unassigned (invalid). | Independent uniform 1–100; 0 = unassigned (invalid) |
| 4 | `RandomInt1000` *(std)* | INTEGER | `>>>9` |  | Y | `0` | Random Int 1000 | Independent uniform random value 1–1000 for selecting ≈ 0.1% subsets. 0 = unassigned (invalid). | Independent uniform 1–1000; 0 = unassigned (invalid) |
| 5 | `CreatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Created At | When the row was created. For historical rows, a synthetic timestamp consistent with the row's business date. | Consistent with the row's business date; NOW for runtime inserts |
| 6 | `CustomerId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Customer Id | Reference to [Customer](Customer.md).`CustomerId` | Random existing parent row, respecting the cardinality |
| 7 | `AddressKind` | CHARACTER | `x(8)` |  | Y | `HOME` | Address Kind | Kind of address | HOME, MAILING, WORK |
| 8 | `AddressLine1` | CHARACTER | `x(60)` |  | Y | `""` | Address Line 1 | First address line | default (data-model §1.5) |
| 9 | `AddressLine2` | CHARACTER | `x(60)` |  | Y | `""` | Address Line 2 | Second address line (apartment, suite) | 20% populated |
| 10 | `City` | CHARACTER | `x(40)` |  | Y | `""` | City | City name | default (data-model §1.5) |
| 11 | `StateProvince` | CHARACTER | `x(30)` |  | Y | `""` | State Province | State or province | default (data-model §1.5) |
| 12 | `PostalCode` | CHARACTER | `x(10)` |  | Y | `""` | Postal Code | Postal / ZIP code | default (data-model §1.5) |
| 13 | `CountryCode` | CHARACTER | `x(2)` |  | Y | `US` | Country Code | ISO country code → [Country](Country.md).`CountryCode` | 95% US |
| 14 | `IsPrimary` | LOGICAL | `yes/no` |  | Y | `no` | Is Primary | Primary entry of its kind for the customer | Exactly one per customer |
| 15 | `ValidFrom` | DATE | `99/99/9999` |  | Y | `?` (unknown) | Valid From | First date the address is valid | default (data-model §1.5) |
| 16 | `ValidTo` | DATE | `99/99/9999` |  | N | `?` (unknown) | Valid To | Last date the address is valid | Unknown = current; 10% past addresses |
| 17 | `UpdatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Updated At | Last modification time; equals CreatedAt right after the load. | Equal to CreatedAt at load |

## Indexes

6 indexes (2 table-specific).

| Name | Components | Primary | Unique | Word | Purpose |
|---|---|---|---|---|---|
| `PkCustomerAddress` *(std)* | CustomerAddressId ASC | Y | Y | N | Single-row random access by sequential ID; default scan order |
| `IxRandomInt10` *(std)* | RandomInt10 ASC, CustomerAddressId ASC | N | N | N | Select ≈ 10% of rows (RandomInt10 = k) |
| `IxRandomInt100` *(std)* | RandomInt100 ASC, CustomerAddressId ASC | N | N | N | Select ≈ 1% of rows (RandomInt100 = k) |
| `IxRandomInt1000` *(std)* | RandomInt1000 ASC, CustomerAddressId ASC | N | N | N | Select ≈ 0.1% of rows (RandomInt1000 = k) |
| `IxCustomer` | CustomerId ASC, AddressKind ASC | N | N | N | A customer's addresses |
| `IxCountryPostal` | CountryCode ASC, PostalCode ASC | N | N | N | Geographic range scans |

## Relationships

**Parents**

- `CustomerId` → [Customer](Customer.md).`CustomerId` — 1.5 / 1–3 children per parent
- `CountryCode` → [Country](Country.md).`CountryCode` — 6,000 / 0–1,425,000 (US 95%) children per parent

**Children**

- none

## Access examples

ABL: about 1% of rows, then one random existing row.

```abl
FOR EACH CustomerAddress NO-LOCK WHERE CustomerAddress.RandomInt100 = 42 USE-INDEX IxRandomInt100:
    /* work */
END.

DEFINE VARIABLE r AS INT64 NO-UNDO.
FIND BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.TableName = "CustomerAddress".
r = RANDOM(1, INTEGER(BenchmarkTableInfo.MaxId)).
FIND CustomerAddress NO-LOCK WHERE CustomerAddress.CustomerAddressId = r NO-ERROR.   /* not AVAILABLE => draw again */
```

SQL:

```sql
SELECT * FROM PUB.CustomerAddress WHERE RandomInt100 = 42;
SELECT MaxId FROM PUB.BenchmarkTableInfo WHERE TableName = 'CustomerAddress';
SELECT * FROM PUB.CustomerAddress WHERE CustomerAddressId = ?;   -- ? drawn uniformly from 1..MaxId
```
