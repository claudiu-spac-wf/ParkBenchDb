# Currency

`Class R (Reference)` · `Tiny` · `Narrow` · `LOB: none`

[← Schema overview](../README.md)

## Description

ISO currencies.

ISO 4217 currencies. Gen: the 40 most-traded currencies; USD is CurrencyId 1.

## Facts

| Property | Value |
|---|---|
| Rows at scale factor 1 | 40 |
| Scaling | fixed (does not change with scale factor) |
| Volume tier | Tiny |
| Estimated average record | 70 bytes (field-by-field estimate: 74 bytes) |
| Record-size tier | Narrow |
| Estimated data at SF 1 | 0.000 GB |
| Data area | `PB_Ref_Data` (RPB 64, BPC 8) |
| Index area | `PB_Ref_Idx` (BPC 8) |
| Sequence | `SeqCurrencyId` (INT64, starts at 1, increment 1, no cycle) |

## Fields

11 fields. *(std)* marks the standard fields present on every table.

| # | Name | Type | Format | Decimals | Mandatory | Initial | Label | Description | Generation |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `CurrencyId` *(std)* | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Currency Id | Dense sequential identifier, 1..N with no gaps after the initial load. Runtime inserts use NEXT-VALUE(SeqCurrencyId). | Assigned 1..N in load order |
| 2 | `RandomInt10` *(std)* | INTEGER | `>9` |  | Y | `0` | Random Int 10 | Independent uniform random value 1–10 for selecting ≈ 10% subsets. 0 = unassigned (invalid). | Independent uniform 1–10; 0 = unassigned (invalid) |
| 3 | `RandomInt100` *(std)* | INTEGER | `>>9` |  | Y | `0` | Random Int 100 | Independent uniform random value 1–100 for selecting ≈ 1% subsets. 0 = unassigned (invalid). | Independent uniform 1–100; 0 = unassigned (invalid) |
| 4 | `RandomInt1000` *(std)* | INTEGER | `>>>9` |  | Y | `0` | Random Int 1000 | Independent uniform random value 1–1000 for selecting ≈ 0.1% subsets. 0 = unassigned (invalid). | Independent uniform 1–1000; 0 = unassigned (invalid) |
| 5 | `CreatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Created At | When the row was created. For historical rows, a synthetic timestamp consistent with the row's business date. | Consistent with the row's business date; NOW for runtime inserts |
| 6 | `CurrencyCode` | CHARACTER | `x(3)` |  | Y | `""` | Currency Code | ISO currency code | ISO alpha code, e.g. USD |
| 7 | `CurrencyName` | CHARACTER | `x(40)` |  | Y | `""` | Currency Name | Currency name | e.g. US Dollar |
| 8 | `NumericCode` | INTEGER | `999` |  | Y | `0` | Numeric Code | ISO numeric code | ISO numeric code |
| 9 | `MinorUnits` | INTEGER | `9` |  | Y | `2` | Minor Units | Decimal places used by the currency | Decimal places (0, 2 or 3) |
| 10 | `CurrencySymbol` | CHARACTER | `x(5)` |  | N | `""` | Currency Symbol | Currency symbol | e.g. $ |
| 11 | `IsActive` | LOGICAL | `yes/no` |  | Y | `yes` | Is Active | Whether the row is active | 95% yes |

## Indexes

5 indexes (1 table-specific).

| Name | Components | Primary | Unique | Word | Purpose |
|---|---|---|---|---|---|
| `PkCurrency` *(std)* | CurrencyId ASC | Y | Y | N | Single-row random access by sequential ID; default scan order |
| `IxRandomInt10` *(std)* | RandomInt10 ASC, CurrencyId ASC | N | N | N | Select ≈ 10% of rows (RandomInt10 = k) |
| `IxRandomInt100` *(std)* | RandomInt100 ASC, CurrencyId ASC | N | N | N | Select ≈ 1% of rows (RandomInt100 = k) |
| `IxRandomInt1000` *(std)* | RandomInt1000 ASC, CurrencyId ASC | N | N | N | Select ≈ 0.1% of rows (RandomInt1000 = k) |
| `UxCurrencyCode` | CurrencyCode ASC | N | Y | N | Lookup by code; target of character FKs |

## Relationships

**Parents**

- none

**Children**

- [Country](Country.md).`DefaultCurrencyCode`
- [ExchangeRate](ExchangeRate.md).`FromCurrencyCode`
- [ExchangeRate](ExchangeRate.md).`ToCurrencyCode`
- [Account](Account.md).`CurrencyCode`
- [CardAuthorization](CardAuthorization.md).`CurrencyCode`

## Access examples

ABL: about 1% of rows, then one random existing row.

```abl
FOR EACH Currency NO-LOCK WHERE Currency.RandomInt100 = 42 USE-INDEX IxRandomInt100:
    /* work */
END.

DEFINE VARIABLE r AS INT64 NO-UNDO.
FIND BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.TableName = "Currency".
r = RANDOM(1, INTEGER(BenchmarkTableInfo.MaxId)).
FIND Currency NO-LOCK WHERE Currency.CurrencyId = r NO-ERROR.   /* not AVAILABLE => draw again */
```

SQL:

```sql
SELECT * FROM PUB.Currency WHERE RandomInt100 = 42;
SELECT MaxId FROM PUB.BenchmarkTableInfo WHERE TableName = 'Currency';
SELECT * FROM PUB.Currency WHERE CurrencyId = ?;   -- ? drawn uniformly from 1..MaxId
```
