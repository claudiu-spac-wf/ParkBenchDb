# Account

`Class M (Master)` · `Medium` · `Standard` · `LOB: none`

[← Schema overview](../README.md)

## Description

A deposit account.

## Facts

| Property | Value |
|---|---|
| Rows at scale factor 1 | 1,500,000 |
| Scaling | linear (rows × scale factor) |
| Volume tier | Medium |
| Estimated average record | 300 bytes (field-by-field estimate: 153 bytes) |
| Record-size tier | Standard |
| Estimated data at SF 1 | 0.450 GB |
| Data area | `PB_Master_Std` (RPB 16, BPC 64) |
| Index area | `PB_Master_Idx` (BPC 64) |
| Sequence | `SeqAccountId` (INT64, starts at 1, increment 1, no cycle) |

## Fields

20 fields. *(std)* marks the standard fields present on every table.

| # | Name | Type | Format | Decimals | Mandatory | Initial | Label | Description | Generation |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `AccountId` *(std)* | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Account Id | Dense sequential identifier, 1..N with no gaps after the initial load. Runtime inserts use NEXT-VALUE(SeqAccountId). | Assigned 1..N in load order |
| 2 | `RandomInt10` *(std)* | INTEGER | `>9` |  | Y | `0` | Random Int 10 | Independent uniform random value 1–10 for selecting ≈ 10% subsets. 0 = unassigned (invalid). | Independent uniform 1–10; 0 = unassigned (invalid) |
| 3 | `RandomInt100` *(std)* | INTEGER | `>>9` |  | Y | `0` | Random Int 100 | Independent uniform random value 1–100 for selecting ≈ 1% subsets. 0 = unassigned (invalid). | Independent uniform 1–100; 0 = unassigned (invalid) |
| 4 | `RandomInt1000` *(std)* | INTEGER | `>>>9` |  | Y | `0` | Random Int 1000 | Independent uniform random value 1–1000 for selecting ≈ 0.1% subsets. 0 = unassigned (invalid). | Independent uniform 1–1000; 0 = unassigned (invalid) |
| 5 | `CreatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Created At | When the row was created. For historical rows, a synthetic timestamp consistent with the row's business date. | Consistent with the row's business date; NOW for runtime inserts |
| 6 | `AccountNumber` | CHARACTER | `x(14)` |  | Y | `""` | Account Number | 12 random digits + 2 check digits | 12 random digits + 2 check digits |
| 7 | `AccountTypeId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Account Type Id | Reference to [AccountType](AccountType.md).`AccountTypeId` | CHECKING 55%, SAVINGS 35%, other 10% |
| 8 | `BranchId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Branch Id | Reference to [Branch](Branch.md).`BranchId` | usually the primary holder's home branch |
| 9 | `CurrencyCode` | CHARACTER | `x(3)` |  | Y | `USD` | Currency Code | ISO currency code → [Currency](Currency.md).`CurrencyCode` | 97% USD |
| 10 | `AccountStatus` | CHARACTER | `x(8)` |  | Y | `OPEN` | Account Status | Lifecycle status | OPEN 92%, DORMANT 5%, FROZEN 0.5%, CLOSED 2.5% |
| 11 | `OpenDate` | DATE | `99/99/9999` |  | Y | `?` (unknown) | Open Date | Date opened | ≥ primary holder's CustomerSince |
| 12 | `CloseDate` | DATE | `99/99/9999` |  | N | `?` (unknown) | Close Date | Date closed | Set only when CLOSED |
| 13 | `CurrentBalance` | DECIMAL | `->>>,>>>,>>>,>>9.99` | 2 | Y | `0` | Current Balance | Equals the last transaction's RunningBalance | Equals the last transaction's RunningBalance |
| 14 | `AvailableBalance` | DECIMAL | `->>>,>>>,>>>,>>9.99` | 2 | Y | `0` | Available Balance | Balance available for withdrawal | CurrentBalance − pending holds |
| 15 | `OverdraftLimit` | DECIMAL | `->>>,>>>,>>>,>>9.99` | 2 | Y | `0` | Overdraft Limit | Approved overdraft limit | default (data-model §1.5) |
| 16 | `InterestRate` | DECIMAL | `>>9.9999` | 4 | Y | `0` | Interest Rate | Annual interest rate (%) | default (data-model §1.5) |
| 17 | `Nickname` | CHARACTER | `x(40)` |  | Y | `""` | Nickname | Customer-chosen account nickname | 30% populated |
| 18 | `LastStatementDate` | DATE | `99/99/9999` |  | N | `?` (unknown) | Last Statement Date | Period end of the most recent statement | default (data-model §1.5) |
| 19 | `LastActivityAt` | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | N | `?` (unknown) | Last Activity At | Time of the most recent transaction | default (data-model §1.5) |
| 20 | `UpdatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Updated At | Last modification time; equals CreatedAt right after the load. | Equal to CreatedAt at load |

## Indexes

8 indexes (4 table-specific).

| Name | Components | Primary | Unique | Word | Purpose |
|---|---|---|---|---|---|
| `PkAccount` *(std)* | AccountId ASC | Y | Y | N | Single-row random access by sequential ID; default scan order |
| `IxRandomInt10` *(std)* | RandomInt10 ASC, AccountId ASC | N | N | N | Select ≈ 10% of rows (RandomInt10 = k) |
| `IxRandomInt100` *(std)* | RandomInt100 ASC, AccountId ASC | N | N | N | Select ≈ 1% of rows (RandomInt100 = k) |
| `IxRandomInt1000` *(std)* | RandomInt1000 ASC, AccountId ASC | N | N | N | Select ≈ 0.1% of rows (RandomInt1000 = k) |
| `UxAccountNumber` | AccountNumber ASC | N | Y | N | Lookup by business key |
| `IxAccountType` | AccountTypeId ASC | N | N | N | Accounts per product |
| `IxBranchStatus` | BranchId ASC, AccountStatus ASC | N | N | N | Branch reporting |
| `IxCurrency` | CurrencyCode ASC | N | N | N | Character-key join to Currency |

## Relationships

**Parents**

- `AccountTypeId` → [AccountType](AccountType.md).`AccountTypeId` — 62,500 / 1,000–450,000 (skewed) children per parent
- `BranchId` → [Branch](Branch.md).`BranchId` — 6,000 / 750–22,500 children per parent
- `CurrencyCode` → [Currency](Currency.md).`CurrencyCode` — 37,500 / 0–1,455,000 (USD 97%) children per parent

**Children**

- [AccountHolder](AccountHolder.md).`AccountId`
- [ScheduledPayment](ScheduledPayment.md).`AccountId`
- [Card](Card.md).`AccountId`
- [Loan](Loan.md).`DisbursementAccountId`
- [AccountStatement](AccountStatement.md).`AccountId`
- [MonthlyBalance](MonthlyBalance.md).`AccountId`
- [CreditTransaction](CreditTransaction.md).`AccountId`
- [Transfer](Transfer.md).`FromAccountId`
- [Transfer](Transfer.md).`ToAccountId`
- [DebitTransaction](DebitTransaction.md).`AccountId`

## Access examples

ABL: about 1% of rows, then one random existing row.

```abl
FOR EACH Account NO-LOCK WHERE Account.RandomInt100 = 42 USE-INDEX IxRandomInt100:
    /* work */
END.

DEFINE VARIABLE r AS INT64 NO-UNDO.
FIND BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.TableName = "Account".
r = RANDOM(1, INTEGER(BenchmarkTableInfo.MaxId)).
FIND Account NO-LOCK WHERE Account.AccountId = r NO-ERROR.   /* not AVAILABLE => draw again */
```

SQL:

```sql
SELECT * FROM PUB.Account WHERE RandomInt100 = 42;
SELECT MaxId FROM PUB.BenchmarkTableInfo WHERE TableName = 'Account';
SELECT * FROM PUB.Account WHERE AccountId = ?;   -- ? drawn uniformly from 1..MaxId
```
