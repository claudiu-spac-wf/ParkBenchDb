# ExchangeRate

`Class R (Reference)` · `Small` · `Narrow` · `LOB: none`

[← Schema overview](../README.md)

## Description

Daily rate between two currencies.

Daily rate from each non-USD currency to USD, over the 12-month history window.

## Facts

| Property | Value |
|---|---|
| Rows at scale factor 1 | 14,235 |
| Scaling | fixed (does not change with scale factor) |
| Volume tier | Small |
| Estimated average record | 70 bytes (field-by-field estimate: 63 bytes) |
| Record-size tier | Narrow |
| Estimated data at SF 1 | 0.001 GB |
| Data area | `PB_Ref_Data` (RPB 64, BPC 8) |
| Index area | `PB_Ref_Idx` (BPC 8) |
| Sequence | `SeqExchangeRateId` (INT64, starts at 1, increment 1, no cycle) |

## Fields

10 fields. *(std)* marks the standard fields present on every table.

| # | Name | Type | Format | Decimals | Mandatory | Initial | Label | Description | Generation |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `ExchangeRateId` *(std)* | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Exchange Rate Id | Dense sequential identifier, 1..N with no gaps after the initial load. Runtime inserts use NEXT-VALUE(SeqExchangeRateId). | Assigned 1..N in load order |
| 2 | `RandomInt10` *(std)* | INTEGER | `>9` |  | Y | `0` | Random Int 10 | Independent uniform random value 1–10 for selecting ≈ 10% subsets. 0 = unassigned (invalid). | Independent uniform 1–10; 0 = unassigned (invalid) |
| 3 | `RandomInt100` *(std)* | INTEGER | `>>9` |  | Y | `0` | Random Int 100 | Independent uniform random value 1–100 for selecting ≈ 1% subsets. 0 = unassigned (invalid). | Independent uniform 1–100; 0 = unassigned (invalid) |
| 4 | `RandomInt1000` *(std)* | INTEGER | `>>>9` |  | Y | `0` | Random Int 1000 | Independent uniform random value 1–1000 for selecting ≈ 0.1% subsets. 0 = unassigned (invalid). | Independent uniform 1–1000; 0 = unassigned (invalid) |
| 5 | `CreatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Created At | When the row was created. For historical rows, a synthetic timestamp consistent with the row's business date. | Consistent with the row's business date; NOW for runtime inserts |
| 6 | `RateDate` | DATE | `99/99/9999` |  | Y | `?` (unknown) | Rate Date | Date the rate applies to | Each day in the window |
| 7 | `FromCurrencyCode` | CHARACTER | `x(3)` |  | Y | `""` | From Currency Code | Reference to [Currency](Currency.md).`CurrencyCode` | every currency except USD |
| 8 | `ToCurrencyCode` | CHARACTER | `x(3)` |  | Y | `""` | To Currency Code | Reference to [Currency](Currency.md).`CurrencyCode` | always USD |
| 9 | `Rate` | DECIMAL | `>>>>>9.99999999` | 8 | Y | `0` | Rate | Exchange rate | Random walk ±0.5% per day from a realistic seed value |
| 10 | `RateSource` | CHARACTER | `x(10)` |  | Y | `""` | Rate Source | Source of the rate | ECB, FED, INTERNAL |

## Indexes

5 indexes (1 table-specific).

| Name | Components | Primary | Unique | Word | Purpose |
|---|---|---|---|---|---|
| `PkExchangeRate` *(std)* | ExchangeRateId ASC | Y | Y | N | Single-row random access by sequential ID; default scan order |
| `IxRandomInt10` *(std)* | RandomInt10 ASC, ExchangeRateId ASC | N | N | N | Select ≈ 10% of rows (RandomInt10 = k) |
| `IxRandomInt100` *(std)* | RandomInt100 ASC, ExchangeRateId ASC | N | N | N | Select ≈ 1% of rows (RandomInt100 = k) |
| `IxRandomInt1000` *(std)* | RandomInt1000 ASC, ExchangeRateId ASC | N | N | N | Select ≈ 0.1% of rows (RandomInt1000 = k) |
| `UxCurrencyPairDate` | FromCurrencyCode ASC, ToCurrencyCode ASC, RateDate DESC | N | Y | N | Latest rate for a pair |

## Relationships

**Parents**

- `FromCurrencyCode` → [Currency](Currency.md).`CurrencyCode` — 356 / 0–365 (USD has 0) children per parent
- `ToCurrencyCode` → [Currency](Currency.md).`CurrencyCode` — 356 / 0–14,235 (all rows reference USD) children per parent; not indexed: Always USD; second component of UxCurrencyPairDate

**Children**

- none

## Access examples

ABL: about 1% of rows, then one random existing row.

```abl
FOR EACH ExchangeRate NO-LOCK WHERE ExchangeRate.RandomInt100 = 42 USE-INDEX IxRandomInt100:
    /* work */
END.

DEFINE VARIABLE r AS INT64 NO-UNDO.
FIND BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.TableName = "ExchangeRate".
r = RANDOM(1, INTEGER(BenchmarkTableInfo.MaxId)).
FIND ExchangeRate NO-LOCK WHERE ExchangeRate.ExchangeRateId = r NO-ERROR.   /* not AVAILABLE => draw again */
```

SQL:

```sql
SELECT * FROM PUB.ExchangeRate WHERE RandomInt100 = 42;
SELECT MaxId FROM PUB.BenchmarkTableInfo WHERE TableName = 'ExchangeRate';
SELECT * FROM PUB.ExchangeRate WHERE ExchangeRateId = ?;   -- ? drawn uniformly from 1..MaxId
```
