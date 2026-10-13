# Merchant

`Class M (Master)` · `Small` · `Standard` · `LOB: none`

[← Schema overview](../README.md)

## Description

Businesses where cards are used.

## Facts

| Property | Value |
|---|---|
| Rows at scale factor 1 | 80,000 |
| Scaling | linear (rows × scale factor) |
| Volume tier | Small |
| Estimated average record | 300 bytes (field-by-field estimate: 169 bytes) |
| Record-size tier | Standard |
| Estimated data at SF 1 | 0.024 GB |
| Data area | `PB_Ref_Data` (RPB 64, BPC 8) |
| Index area | `PB_Ref_Idx` (BPC 8) |
| Sequence | `SeqMerchantId` (INT64, starts at 1, increment 1, no cycle) |

## Fields

17 fields. *(std)* marks the standard fields present on every table.

| # | Name | Type | Format | Decimals | Mandatory | Initial | Label | Description | Generation |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `MerchantId` *(std)* | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Merchant Id | Dense sequential identifier, 1..N with no gaps after the initial load. Runtime inserts use NEXT-VALUE(SeqMerchantId). | Assigned 1..N in load order |
| 2 | `RandomInt10` *(std)* | INTEGER | `>9` |  | Y | `0` | Random Int 10 | Independent uniform random value 1–10 for selecting ≈ 10% subsets. 0 = unassigned (invalid). | Independent uniform 1–10; 0 = unassigned (invalid) |
| 3 | `RandomInt100` *(std)* | INTEGER | `>>9` |  | Y | `0` | Random Int 100 | Independent uniform random value 1–100 for selecting ≈ 1% subsets. 0 = unassigned (invalid). | Independent uniform 1–100; 0 = unassigned (invalid) |
| 4 | `RandomInt1000` *(std)* | INTEGER | `>>>9` |  | Y | `0` | Random Int 1000 | Independent uniform random value 1–1000 for selecting ≈ 0.1% subsets. 0 = unassigned (invalid). | Independent uniform 1–1000; 0 = unassigned (invalid) |
| 5 | `CreatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Created At | When the row was created. For historical rows, a synthetic timestamp consistent with the row's business date. | Consistent with the row's business date; NOW for runtime inserts |
| 6 | `MerchantNumber` | CHARACTER | `x(15)` |  | Y | `""` | Merchant Number | Merchant business key | M + 14 digits |
| 7 | `MerchantName` | CHARACTER | `x(80)` |  | Y | `""` | Merchant Name | Merchant trading name | 2–5 words from a business-name word list (feeds the word index) |
| 8 | `MerchantCategoryId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Merchant Category Id | Reference to [MerchantCategory](MerchantCategory.md).`MerchantCategoryId` | Zipf-skewed |
| 9 | `City` | CHARACTER | `x(40)` |  | Y | `""` | City | City name | default (data-model §1.5) |
| 10 | `StateProvince` | CHARACTER | `x(30)` |  | Y | `""` | State Province | State or province | default (data-model §1.5) |
| 11 | `PostalCode` | CHARACTER | `x(10)` |  | Y | `""` | Postal Code | Postal / ZIP code | default (data-model §1.5) |
| 12 | `CountryCode` | CHARACTER | `x(2)` |  | Y | `""` | Country Code | ISO country code → [Country](Country.md).`CountryCode` | 85% US |
| 13 | `Latitude` | DECIMAL | `->>9.999999` | 6 | Y | `0` | Latitude | Latitude (WGS84) | default (data-model §1.5) |
| 14 | `Longitude` | DECIMAL | `->>9.999999` | 6 | Y | `0` | Longitude | Longitude (WGS84) | default (data-model §1.5) |
| 15 | `IsOnline` | LOGICAL | `yes/no` |  | Y | `no` | Is Online | Online-only merchant | 25% yes |
| 16 | `RiskScore` | INTEGER | `>>9` |  | Y | `0` | Risk Score | Merchant risk score | 0–100, normal around 20 |
| 17 | `UpdatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Updated At | Last modification time; equals CreatedAt right after the load. | Equal to CreatedAt at load |

## Indexes

8 indexes (4 table-specific).

| Name | Components | Primary | Unique | Word | Purpose |
|---|---|---|---|---|---|
| `PkMerchant` *(std)* | MerchantId ASC | Y | Y | N | Single-row random access by sequential ID; default scan order |
| `IxRandomInt10` *(std)* | RandomInt10 ASC, MerchantId ASC | N | N | N | Select ≈ 10% of rows (RandomInt10 = k) |
| `IxRandomInt100` *(std)* | RandomInt100 ASC, MerchantId ASC | N | N | N | Select ≈ 1% of rows (RandomInt100 = k) |
| `IxRandomInt1000` *(std)* | RandomInt1000 ASC, MerchantId ASC | N | N | N | Select ≈ 0.1% of rows (RandomInt1000 = k) |
| `UxMerchantNumber` | MerchantNumber ASC | N | Y | N | Lookup |
| `IxCategory` | MerchantCategoryId ASC | N | N | N | Merchants per MCC |
| `IxCountryCity` | CountryCode ASC, City ASC | N | N | N | Geographic |
| `WxMerchantName` | MerchantName ASC | N | N | Y | CONTAINS search |

## Relationships

**Parents**

- `MerchantCategoryId` → [MerchantCategory](MerchantCategory.md).`MerchantCategoryId` — 133 / 0–2,000 (skewed) children per parent
- `CountryCode` → [Country](Country.md).`CountryCode` — 320 / 0–68,000 (US 85%) children per parent

**Children**

- [DebitTransaction](DebitTransaction.md).`MerchantId`
- [CardAuthorization](CardAuthorization.md).`MerchantId`

## Access examples

ABL: about 1% of rows, then one random existing row.

```abl
FOR EACH Merchant NO-LOCK WHERE Merchant.RandomInt100 = 42 USE-INDEX IxRandomInt100:
    /* work */
END.

DEFINE VARIABLE r AS INT64 NO-UNDO.
FIND BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.TableName = "Merchant".
r = RANDOM(1, INTEGER(BenchmarkTableInfo.MaxId)).
FIND Merchant NO-LOCK WHERE Merchant.MerchantId = r NO-ERROR.   /* not AVAILABLE => draw again */
```

SQL:

```sql
SELECT * FROM PUB.Merchant WHERE RandomInt100 = 42;
SELECT MaxId FROM PUB.BenchmarkTableInfo WHERE TableName = 'Merchant';
SELECT * FROM PUB.Merchant WHERE MerchantId = ?;   -- ? drawn uniformly from 1..MaxId
```
