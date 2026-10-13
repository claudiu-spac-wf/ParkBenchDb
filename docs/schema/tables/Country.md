# Country

`Class R (Reference)` · `Tiny` · `Narrow` · `LOB: none`

[← Schema overview](../README.md)

## Description

ISO countries with default currency.

## Facts

| Property | Value |
|---|---|
| Rows at scale factor 1 | 250 |
| Scaling | fixed (does not change with scale factor) |
| Volume tier | Tiny |
| Estimated average record | 80 bytes (field-by-field estimate: 79 bytes) |
| Record-size tier | Narrow |
| Estimated data at SF 1 | 0.000 GB |
| Data area | `PB_Ref_Data` (RPB 64, BPC 8) |
| Index area | `PB_Ref_Idx` (BPC 8) |
| Sequence | `SeqCountryId` (INT64, starts at 1, increment 1, no cycle) |

## Fields

9 fields. *(std)* marks the standard fields present on every table.

| # | Name | Type | Format | Decimals | Mandatory | Initial | Label | Description | Generation |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `CountryId` *(std)* | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Country Id | Dense sequential identifier, 1..N with no gaps after the initial load. Runtime inserts use NEXT-VALUE(SeqCountryId). | Assigned 1..N in load order |
| 2 | `RandomInt10` *(std)* | INTEGER | `>9` |  | Y | `0` | Random Int 10 | Independent uniform random value 1–10 for selecting ≈ 10% subsets. 0 = unassigned (invalid). | Independent uniform 1–10; 0 = unassigned (invalid) |
| 3 | `RandomInt100` *(std)* | INTEGER | `>>9` |  | Y | `0` | Random Int 100 | Independent uniform random value 1–100 for selecting ≈ 1% subsets. 0 = unassigned (invalid). | Independent uniform 1–100; 0 = unassigned (invalid) |
| 4 | `RandomInt1000` *(std)* | INTEGER | `>>>9` |  | Y | `0` | Random Int 1000 | Independent uniform random value 1–1000 for selecting ≈ 0.1% subsets. 0 = unassigned (invalid). | Independent uniform 1–1000; 0 = unassigned (invalid) |
| 5 | `CreatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Created At | When the row was created. For historical rows, a synthetic timestamp consistent with the row's business date. | Consistent with the row's business date; NOW for runtime inserts |
| 6 | `CountryCode` | CHARACTER | `x(2)` |  | Y | `""` | Country Code | ISO country code | ISO 3166 alpha-2 |
| 7 | `CountryName` | CHARACTER | `x(60)` |  | Y | `""` | Country Name | Country name | default (data-model §1.5) |
| 8 | `DefaultCurrencyCode` | CHARACTER | `x(3)` |  | Y | `""` | Default Currency Code | Reference to [Currency](Currency.md).`CurrencyCode` | Random existing parent row, respecting the cardinality |
| 9 | `PhonePrefix` | CHARACTER | `x(6)` |  | N | `""` | Phone Prefix | International dialling prefix | e.g. +1 |

## Indexes

6 indexes (2 table-specific).

| Name | Components | Primary | Unique | Word | Purpose |
|---|---|---|---|---|---|
| `PkCountry` *(std)* | CountryId ASC | Y | Y | N | Single-row random access by sequential ID; default scan order |
| `IxRandomInt10` *(std)* | RandomInt10 ASC, CountryId ASC | N | N | N | Select ≈ 10% of rows (RandomInt10 = k) |
| `IxRandomInt100` *(std)* | RandomInt100 ASC, CountryId ASC | N | N | N | Select ≈ 1% of rows (RandomInt100 = k) |
| `IxRandomInt1000` *(std)* | RandomInt1000 ASC, CountryId ASC | N | N | N | Select ≈ 0.1% of rows (RandomInt1000 = k) |
| `UxCountryCode` | CountryCode ASC | N | Y | N | Lookup by code |
| `IxDefaultCurrency` | DefaultCurrencyCode ASC | N | N | N | Countries using a currency |

## Relationships

**Parents**

- `DefaultCurrencyCode` → [Currency](Currency.md).`CurrencyCode` — 6 / 1–60 children per parent

**Children**

- [Branch](Branch.md).`CountryCode`
- [Merchant](Merchant.md).`CountryCode`
- [CustomerAddress](CustomerAddress.md).`CountryCode`
- [CustomerDocument](CustomerDocument.md).`IssuingCountryCode`

## Access examples

ABL: about 1% of rows, then one random existing row.

```abl
FOR EACH Country NO-LOCK WHERE Country.RandomInt100 = 42 USE-INDEX IxRandomInt100:
    /* work */
END.

DEFINE VARIABLE r AS INT64 NO-UNDO.
FIND BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.TableName = "Country".
r = RANDOM(1, INTEGER(BenchmarkTableInfo.MaxId)).
FIND Country NO-LOCK WHERE Country.CountryId = r NO-ERROR.   /* not AVAILABLE => draw again */
```

SQL:

```sql
SELECT * FROM PUB.Country WHERE RandomInt100 = 42;
SELECT MaxId FROM PUB.BenchmarkTableInfo WHERE TableName = 'Country';
SELECT * FROM PUB.Country WHERE CountryId = ?;   -- ? drawn uniformly from 1..MaxId
```
