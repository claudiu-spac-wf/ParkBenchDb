# Card

`Class M (Master)` · `Medium` · `Standard` · `LOB: none`

[← Schema overview](../README.md)

## Description

Debit/credit cards.

## Facts

| Property | Value |
|---|---|
| Rows at scale factor 1 | 1,200,000 |
| Scaling | linear (rows × scale factor) |
| Volume tier | Medium |
| Estimated average record | 230 bytes (field-by-field estimate: 141 bytes) |
| Record-size tier | Standard |
| Estimated data at SF 1 | 0.276 GB |
| Data area | `PB_Master_Std` (RPB 16, BPC 64) |
| Index area | `PB_Master_Idx` (BPC 64) |
| Sequence | `SeqCardId` (INT64, starts at 1, increment 1, no cycle) |

## Fields

19 fields. *(std)* marks the standard fields present on every table.

| # | Name | Type | Format | Decimals | Mandatory | Initial | Label | Description | Generation |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `CardId` *(std)* | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Card Id | Dense sequential identifier, 1..N with no gaps after the initial load. Runtime inserts use NEXT-VALUE(SeqCardId). | Assigned 1..N in load order |
| 2 | `RandomInt10` *(std)* | INTEGER | `>9` |  | Y | `0` | Random Int 10 | Independent uniform random value 1–10 for selecting ≈ 10% subsets. 0 = unassigned (invalid). | Independent uniform 1–10; 0 = unassigned (invalid) |
| 3 | `RandomInt100` *(std)* | INTEGER | `>>9` |  | Y | `0` | Random Int 100 | Independent uniform random value 1–100 for selecting ≈ 1% subsets. 0 = unassigned (invalid). | Independent uniform 1–100; 0 = unassigned (invalid) |
| 4 | `RandomInt1000` *(std)* | INTEGER | `>>>9` |  | Y | `0` | Random Int 1000 | Independent uniform random value 1–1000 for selecting ≈ 0.1% subsets. 0 = unassigned (invalid). | Independent uniform 1–1000; 0 = unassigned (invalid) |
| 5 | `CreatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Created At | When the row was created. For historical rows, a synthetic timestamp consistent with the row's business date. | Consistent with the row's business date; NOW for runtime inserts |
| 6 | `CardToken` | CHARACTER | `x(32)` |  | Y | `""` | Card Token | Random 32-character hex; unique | Random 32-character hex; unique |
| 7 | `CardNumberMasked` | CHARACTER | `x(19)` |  | Y | `""` | Card Number Masked | Masked card number | **** **** **** 1234 |
| 8 | `AccountId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Account Id | Reference to [Account](Account.md).`AccountId` | Random existing parent row, respecting the cardinality |
| 9 | `CustomerId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Customer Id | Reference to [Customer](Customer.md).`CustomerId` | Random existing parent row, respecting the cardinality |
| 10 | `CardKind` | CHARACTER | `x(8)` |  | Y | `DEBIT` | Card Kind | Kind of card | DEBIT 85%, CREDIT 12%, PREPAID 3% |
| 11 | `Network` | CHARACTER | `x(10)` |  | Y | `""` | Network | Card network | VISA, MC, AMEX, DISCOVER |
| 12 | `EmbossedName` | CHARACTER | `x(26)` |  | Y | `""` | Embossed Name | Name printed on the card | default (data-model §1.5) |
| 13 | `ExpiryMonth` | INTEGER | `99` |  | Y | `0` | Expiry Month | Card expiry month | 1–12 |
| 14 | `ExpiryYear` | INTEGER | `9999` |  | Y | `0` | Expiry Year | Card expiry year | default (data-model §1.5) |
| 15 | `IssueDate` | DATE | `99/99/9999` |  | Y | `?` (unknown) | Issue Date | Date issued | default (data-model §1.5) |
| 16 | `CardStatus` | CHARACTER | `x(10)` |  | Y | `ACTIVE` | Card Status | Lifecycle status | ACTIVE 88%, LOCKED 2%, EXPIRED 6%, CANCELLED 4% |
| 17 | `DailyLimit` | DECIMAL | `->>>,>>>,>>>,>>9.99` | 2 | Y | `0` | Daily Limit | Daily spending limit | 500–10,000 |
| 18 | `IsContactless` | LOGICAL | `yes/no` |  | Y | `yes` | Is Contactless | Whether the card supports contactless payment | default (data-model §1.5) |
| 19 | `UpdatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Updated At | Last modification time; equals CreatedAt right after the load. | Equal to CreatedAt at load |

## Indexes

7 indexes (3 table-specific).

| Name | Components | Primary | Unique | Word | Purpose |
|---|---|---|---|---|---|
| `PkCard` *(std)* | CardId ASC | Y | Y | N | Single-row random access by sequential ID; default scan order |
| `IxRandomInt10` *(std)* | RandomInt10 ASC, CardId ASC | N | N | N | Select ≈ 10% of rows (RandomInt10 = k) |
| `IxRandomInt100` *(std)* | RandomInt100 ASC, CardId ASC | N | N | N | Select ≈ 1% of rows (RandomInt100 = k) |
| `IxRandomInt1000` *(std)* | RandomInt1000 ASC, CardId ASC | N | N | N | Select ≈ 0.1% of rows (RandomInt1000 = k) |
| `UxCardToken` | CardToken ASC | N | Y | N | Authorization lookup (random character key) |
| `IxAccount` | AccountId ASC | N | N | N | An account's cards |
| `IxCustomer` | CustomerId ASC | N | N | N | A customer's cards |

## Relationships

**Parents**

- `AccountId` → [Account](Account.md).`AccountId` — 0.8 / 0–3 children per parent
- `CustomerId` → [Customer](Customer.md).`CustomerId` — 1.2 / 0–4 children per parent

**Children**

- [CardAuthorization](CardAuthorization.md).`CardId`

## Access examples

ABL: about 1% of rows, then one random existing row.

```abl
FOR EACH Card NO-LOCK WHERE Card.RandomInt100 = 42 USE-INDEX IxRandomInt100:
    /* work */
END.

DEFINE VARIABLE r AS INT64 NO-UNDO.
FIND BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.TableName = "Card".
r = RANDOM(1, INTEGER(BenchmarkTableInfo.MaxId)).
FIND Card NO-LOCK WHERE Card.CardId = r NO-ERROR.   /* not AVAILABLE => draw again */
```

SQL:

```sql
SELECT * FROM PUB.Card WHERE RandomInt100 = 42;
SELECT MaxId FROM PUB.BenchmarkTableInfo WHERE TableName = 'Card';
SELECT * FROM PUB.Card WHERE CardId = ?;   -- ? drawn uniformly from 1..MaxId
```
