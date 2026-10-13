# CustomerDocument

`Class M (Master)` · `Medium` · `LOB-bearing` · `LOB: BLOB`

[← Schema overview](../README.md)

## Description

Identity documents and scans.

## Facts

| Property | Value |
|---|---|
| Rows at scale factor 1 | 1,000,000 |
| Scaling | linear (rows × scale factor) |
| Volume tier | Medium |
| Estimated average record | 200 bytes (field-by-field estimate: 175 bytes) |
| Record-size tier | LOB-bearing |
| Estimated data at SF 1 | 0.200 GB |
| Estimated LOB content at SF 1 | 1.638 GB |
| Data area | `PB_Master_Std` (RPB 16, BPC 64) |
| Index area | `PB_Master_Idx` (BPC 64) |
| LOB areas | `PB_Lob_Doc` (BPC 512) |
| Sequence | `SeqCustomerDocumentId` (INT64, starts at 1, increment 1, no cycle) |

## Fields

18 fields. *(std)* marks the standard fields present on every table.

| # | Name | Type | Format | Decimals | Mandatory | Initial | Label | Description | Generation |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `CustomerDocumentId` *(std)* | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Customer Document Id | Dense sequential identifier, 1..N with no gaps after the initial load. Runtime inserts use NEXT-VALUE(SeqCustomerDocumentId). | Assigned 1..N in load order |
| 2 | `RandomInt10` *(std)* | INTEGER | `>9` |  | Y | `0` | Random Int 10 | Independent uniform random value 1–10 for selecting ≈ 10% subsets. 0 = unassigned (invalid). | Independent uniform 1–10; 0 = unassigned (invalid) |
| 3 | `RandomInt100` *(std)* | INTEGER | `>>9` |  | Y | `0` | Random Int 100 | Independent uniform random value 1–100 for selecting ≈ 1% subsets. 0 = unassigned (invalid). | Independent uniform 1–100; 0 = unassigned (invalid) |
| 4 | `RandomInt1000` *(std)* | INTEGER | `>>>9` |  | Y | `0` | Random Int 1000 | Independent uniform random value 1–1000 for selecting ≈ 0.1% subsets. 0 = unassigned (invalid). | Independent uniform 1–1000; 0 = unassigned (invalid) |
| 5 | `CreatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Created At | When the row was created. For historical rows, a synthetic timestamp consistent with the row's business date. | Consistent with the row's business date; NOW for runtime inserts |
| 6 | `CustomerId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Customer Id | Reference to [Customer](Customer.md).`CustomerId` | Random existing parent row, respecting the cardinality |
| 7 | `DocumentKind` | CHARACTER | `x(12)` |  | Y | `""` | Document Kind | PASSPORT, DRIVERLIC, UTILITYBILL, TAXFORM, OTHER | PASSPORT, DRIVERLIC, UTILITYBILL, TAXFORM, OTHER |
| 8 | `DocumentNumberMasked` | CHARACTER | `x(20)` |  | Y | `""` | Document Number Masked | Masked document number | default (data-model §1.5) |
| 9 | `IssuingCountryCode` | CHARACTER | `x(2)` |  | Y | `US` | Issuing Country Code | Country that issued the document → [Country](Country.md).`CountryCode` | Random existing parent row, respecting the cardinality |
| 10 | `IssueDate` | DATE | `99/99/9999` |  | N | `?` (unknown) | Issue Date | Date issued | default (data-model §1.5) |
| 11 | `ExpiryDate` | DATE | `99/99/9999` |  | N | `?` (unknown) | Expiry Date | Document expiry date | Passports/licences only; 5% expired |
| 12 | `VerificationStatus` | CHARACTER | `x(10)` |  | Y | `PENDING` | Verification Status | Verification status | VERIFIED 90%, PENDING 7%, REJECTED 3% |
| 13 | `VerifiedByEmployeeId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Verified By Employee Id | Reference to [Employee](Employee.md).`EmployeeId` | Random existing parent row, respecting the cardinality |
| 14 | `MimeType` | CHARACTER | `x(40)` |  | Y | `""` | Mime Type | MIME type of the stored content | image/jpeg, image/png, application/pdf |
| 15 | `FileName` | CHARACTER | `x(80)` |  | Y | `""` | File Name | Original file name | default (data-model §1.5) |
| 16 | `FileSizeBytes` | INT64 | `>>>>>>>>>9` |  | Y | `0` | File Size Bytes | Equals the Content length; 0 when absent | Equals the Content length; 0 when absent |
| 17 | `Content` | BLOB | – |  | N | `?` (unknown) | Content | Present on 10% of rows; 4–64 KB (avg 16 KB). Area PB_Lob_Doc | Present on 10% of rows; 4–64 KB (avg 16 KB). Area PB_Lob_Doc |
| 18 | `UpdatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Updated At | Last modification time; equals CreatedAt right after the load. | Equal to CreatedAt at load |

## LOB fields

| Field | Type | Area | Max size | Codepage | Content | Populated | Min / Avg / Max bytes |
|---|---|---|---|---|---|---|---|
| `Content` | BLOB | `PB_Lob_Doc` | 64K | – | JPEG/PNG/PDF | 10% | 4,096 / 16,384 / 65,536 |

## Indexes

6 indexes (2 table-specific).

| Name | Components | Primary | Unique | Word | Purpose |
|---|---|---|---|---|---|
| `PkCustomerDocument` *(std)* | CustomerDocumentId ASC | Y | Y | N | Single-row random access by sequential ID; default scan order |
| `IxRandomInt10` *(std)* | RandomInt10 ASC, CustomerDocumentId ASC | N | N | N | Select ≈ 10% of rows (RandomInt10 = k) |
| `IxRandomInt100` *(std)* | RandomInt100 ASC, CustomerDocumentId ASC | N | N | N | Select ≈ 1% of rows (RandomInt100 = k) |
| `IxRandomInt1000` *(std)* | RandomInt1000 ASC, CustomerDocumentId ASC | N | N | N | Select ≈ 0.1% of rows (RandomInt1000 = k) |
| `IxCustomer` | CustomerId ASC, DocumentKind ASC | N | N | N | A customer's documents |
| `IxExpiry` | ExpiryDate ASC | N | N | N | Expiring-document batch job |

## Relationships

**Parents**

- `CustomerId` → [Customer](Customer.md).`CustomerId` — 1.0 / 0–3 children per parent
- `IssuingCountryCode` → [Country](Country.md).`CountryCode` — 4,000 / 0–950,000 (US 95%) children per parent; not indexed: Lookup to Country only
- `VerifiedByEmployeeId` → [Employee](Employee.md).`EmployeeId` — 200 / 0–1,000 children per parent; not indexed: Lookup to Employee only

**Children**

- none

## Access examples

ABL: about 1% of rows, then one random existing row.

```abl
FOR EACH CustomerDocument NO-LOCK WHERE CustomerDocument.RandomInt100 = 42 USE-INDEX IxRandomInt100:
    /* work */
END.

DEFINE VARIABLE r AS INT64 NO-UNDO.
FIND BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.TableName = "CustomerDocument".
r = RANDOM(1, INTEGER(BenchmarkTableInfo.MaxId)).
FIND CustomerDocument NO-LOCK WHERE CustomerDocument.CustomerDocumentId = r NO-ERROR.   /* not AVAILABLE => draw again */
```

SQL:

```sql
SELECT * FROM PUB.CustomerDocument WHERE RandomInt100 = 42;
SELECT MaxId FROM PUB.BenchmarkTableInfo WHERE TableName = 'CustomerDocument';
SELECT * FROM PUB.CustomerDocument WHERE CustomerDocumentId = ?;   -- ? drawn uniformly from 1..MaxId
```
