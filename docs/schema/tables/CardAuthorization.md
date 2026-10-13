# CardAuthorization

`Class T (Transactional)` · `Very Large` · `Narrow` · `LOB: none`

[← Schema overview](../README.md)

## Description

Card authorization requests.

## Facts

| Property | Value |
|---|---|
| Rows at scale factor 1 | 50,000,000 |
| Scaling | linear (rows × scale factor) |
| Volume tier | Very Large |
| Estimated average record | 100 bytes (field-by-field estimate: 103 bytes) |
| Record-size tier | Narrow |
| Estimated data at SF 1 | 5.000 GB |
| Data area | `PB_Txn_CardAuth` (RPB 64, BPC 512) |
| Index area | `PB_Txn_Idx` (BPC 512) |
| Sequence | `SeqCardAuthorizationId` (INT64, starts at 1, increment 1, no cycle) |

## Fields

17 fields. *(std)* marks the standard fields present on every table.

| # | Name | Type | Format | Decimals | Mandatory | Initial | Label | Description | Generation |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `CardAuthorizationId` *(std)* | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Card Authorization Id | Dense sequential identifier, 1..N with no gaps after the initial load. Runtime inserts use NEXT-VALUE(SeqCardAuthorizationId). | Assigned 1..N in load order |
| 2 | `RandomInt10` *(std)* | INTEGER | `>9` |  | Y | `0` | Random Int 10 | Independent uniform random value 1–10 for selecting ≈ 10% subsets. 0 = unassigned (invalid). | Independent uniform 1–10; 0 = unassigned (invalid) |
| 3 | `RandomInt100` *(std)* | INTEGER | `>>9` |  | Y | `0` | Random Int 100 | Independent uniform random value 1–100 for selecting ≈ 1% subsets. 0 = unassigned (invalid). | Independent uniform 1–100; 0 = unassigned (invalid) |
| 4 | `RandomInt1000` *(std)* | INTEGER | `>>>9` |  | Y | `0` | Random Int 1000 | Independent uniform random value 1–1000 for selecting ≈ 0.1% subsets. 0 = unassigned (invalid). | Independent uniform 1–1000; 0 = unassigned (invalid) |
| 5 | `CreatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Created At | When the row was created. For historical rows, a synthetic timestamp consistent with the row's business date. | Consistent with the row's business date; NOW for runtime inserts |
| 6 | `CardId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Card Id | Reference to [Card](Card.md).`CardId` | Random existing parent row, respecting the cardinality |
| 7 | `MerchantId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Merchant Id | Reference to [Merchant](Merchant.md).`MerchantId` | Random existing parent row, respecting the cardinality |
| 8 | `AuthDateTime` | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `?` (unknown) | Auth Date Time | When the authorization was requested (UTC offset kept) | default (data-model §1.5) |
| 9 | `MerchantLocalDateTime` | DATETIME | `99/99/9999 HH:MM:SS.SSS` |  | Y | `?` (unknown) | Merchant Local Date Time | AuthDateTime in the merchant's local zone, stored without an offset | AuthDateTime in the merchant's local zone, stored without an offset |
| 10 | `Amount` | DECIMAL | `->>>,>>>,>>>,>>9.99` | 2 | Y | `0` | Amount | Amount authorized, in CurrencyCode | default (data-model §1.5) |
| 11 | `CurrencyCode` | CHARACTER | `x(3)` |  | Y | `USD` | Currency Code | ISO currency code → [Currency](Currency.md).`CurrencyCode` | 95% USD |
| 12 | `AuthCode` | CHARACTER | `x(6)` |  | Y | `""` | Auth Code | Authorization code returned by the issuer | Empty when declined |
| 13 | `ResponseCode` | CHARACTER | `x(2)` |  | Y | `00` | Response Code | 00 approved 94%; 05, 51, 54, 61 declined | 00 approved 94%; 05, 51, 54, 61 declined |
| 14 | `IsApproved` | LOGICAL | `yes/no` |  | Y | `yes` | Is Approved | Whether the authorization was approved | default (data-model §1.5) |
| 15 | `EntryMode` | CHARACTER | `x(4)` |  | Y | `CHIP` | Entry Mode | CHIP, SWIP, TAP, ECOM | CHIP, SWIP, TAP, ECOM |
| 16 | `AuthKind` | CHARACTER | `x(9)` |  | Y | `FINAL` | Auth Kind | FINAL 56%, PREAUTH 22%, INCREMENT 10%, REVERSAL 12% | FINAL 56%, PREAUTH 22%, INCREMENT 10%, REVERSAL 12% |
| 17 | `DebitTransactionId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Debit Transaction Id | Reference to [DebitTransaction](DebitTransaction.md).`DebitTransactionId` | set only on approved FINAL auths (≈ 50% of rows, exactly one per POS debit); otherwise 0 |

## Indexes

6 indexes (2 table-specific).

| Name | Components | Primary | Unique | Word | Purpose |
|---|---|---|---|---|---|
| `PkCardAuthorization` *(std)* | CardAuthorizationId ASC | Y | Y | N | Single-row random access by sequential ID; default scan order |
| `IxRandomInt10` *(std)* | RandomInt10 ASC, CardAuthorizationId ASC | N | N | N | Select ≈ 10% of rows (RandomInt10 = k) |
| `IxRandomInt100` *(std)* | RandomInt100 ASC, CardAuthorizationId ASC | N | N | N | Select ≈ 1% of rows (RandomInt100 = k) |
| `IxRandomInt1000` *(std)* | RandomInt1000 ASC, CardAuthorizationId ASC | N | N | N | Select ≈ 0.1% of rows (RandomInt1000 = k) |
| `IxCardDate` | CardId ASC, AuthDateTime DESC | N | N | N | Recent auths for a card (fraud check) |
| `IxMerchantDate` | MerchantId ASC, AuthDateTime ASC | N | N | N | Merchant settlement |

## Relationships

**Parents**

- `CardId` → [Card](Card.md).`CardId` — 42 / 0–500 children per parent
- `MerchantId` → [Merchant](Merchant.md).`MerchantId` — 625 / 0–80,000 (Zipf) children per parent
- `CurrencyCode` → [Currency](Currency.md).`CurrencyCode` — 1,250,000 / 0–47,500,000 (USD 95%) children per parent; not indexed: Lookup to Currency only
- `DebitTransactionId` → [DebitTransaction](DebitTransaction.md).`DebitTransactionId` — 0.5 / 0–1 children per parent; optional (0 = none); not indexed: Lookup to DebitTransaction only

**Children**

- none

## Access examples

ABL: about 1% of rows, then one random existing row.

```abl
FOR EACH CardAuthorization NO-LOCK WHERE CardAuthorization.RandomInt100 = 42 USE-INDEX IxRandomInt100:
    /* work */
END.

DEFINE VARIABLE r AS INT64 NO-UNDO.
FIND BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.TableName = "CardAuthorization".
r = RANDOM(1, INTEGER(BenchmarkTableInfo.MaxId)).
FIND CardAuthorization NO-LOCK WHERE CardAuthorization.CardAuthorizationId = r NO-ERROR.   /* not AVAILABLE => draw again */
```

SQL:

```sql
SELECT * FROM PUB.CardAuthorization WHERE RandomInt100 = 42;
SELECT MaxId FROM PUB.BenchmarkTableInfo WHERE TableName = 'CardAuthorization';
SELECT * FROM PUB.CardAuthorization WHERE CardAuthorizationId = ?;   -- ? drawn uniformly from 1..MaxId
```
