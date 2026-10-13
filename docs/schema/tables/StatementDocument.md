# StatementDocument

`Class T (Transactional)` · `Medium` · `LOB-bearing` · `LOB: CLOB + BLOB`

[← Schema overview](../README.md)

## Description

Rendered statement file.

The rendered copy of the **most recent** statement, for paperless accounts that requested a PDF (≈ 10% of accounts).

## Facts

| Property | Value |
|---|---|
| Rows at scale factor 1 | 150,000 |
| Scaling | linear (rows × scale factor) |
| Volume tier | Medium |
| Estimated average record | 160 bytes (field-by-field estimate: 119 bytes) |
| Record-size tier | LOB-bearing |
| Estimated data at SF 1 | 0.024 GB |
| Estimated LOB content at SF 1 | 1.690 GB |
| Data area | `PB_Master_Std` (RPB 16, BPC 64) |
| Index area | `PB_Master_Idx` (BPC 64) |
| LOB areas | `PB_Lob_Stmt` (BPC 512) |
| Sequence | `SeqStatementDocumentId` (INT64, starts at 1, increment 1, no cycle) |

## Fields

12 fields. *(std)* marks the standard fields present on every table.

| # | Name | Type | Format | Decimals | Mandatory | Initial | Label | Description | Generation |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `StatementDocumentId` *(std)* | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Statement Document Id | Dense sequential identifier, 1..N with no gaps after the initial load. Runtime inserts use NEXT-VALUE(SeqStatementDocumentId). | Assigned 1..N in load order |
| 2 | `RandomInt10` *(std)* | INTEGER | `>9` |  | Y | `0` | Random Int 10 | Independent uniform random value 1–10 for selecting ≈ 10% subsets. 0 = unassigned (invalid). | Independent uniform 1–10; 0 = unassigned (invalid) |
| 3 | `RandomInt100` *(std)* | INTEGER | `>>9` |  | Y | `0` | Random Int 100 | Independent uniform random value 1–100 for selecting ≈ 1% subsets. 0 = unassigned (invalid). | Independent uniform 1–100; 0 = unassigned (invalid) |
| 4 | `RandomInt1000` *(std)* | INTEGER | `>>>9` |  | Y | `0` | Random Int 1000 | Independent uniform random value 1–1000 for selecting ≈ 0.1% subsets. 0 = unassigned (invalid). | Independent uniform 1–1000; 0 = unassigned (invalid) |
| 5 | `CreatedAt` *(std)* | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `NOW` | Created At | When the row was created. For historical rows, a synthetic timestamp consistent with the row's business date. | Consistent with the row's business date; NOW for runtime inserts |
| 6 | `AccountStatementId` | INT64 | `>>>>>>>>>>>9` |  | Y | `0` | Account Statement Id | Reference to [AccountStatement](AccountStatement.md).`AccountStatementId` | unique |
| 7 | `DocumentFormat` | CHARACTER | `x(8)` |  | Y | `PDF` | Document Format | Always PDF at load | Always PDF at load |
| 8 | `PageCount` | INTEGER | `>>9` |  | Y | `0` | Page Count | Number of pages | 1–6 |
| 9 | `Checksum` | CHARACTER | `x(64)` |  | Y | `""` | Checksum | SHA-256 hex of PdfContent | SHA-256 hex of PdfContent |
| 10 | `RenderedAt` | DATETIME-TZ | `99/99/9999 HH:MM:SS.SSS+HH:MM` |  | Y | `?` (unknown) | Rendered At | When the document was rendered | default (data-model §1.5) |
| 11 | `PdfContent` | BLOB | – |  | Y | `?` (unknown) | Pdf Content | Always present; 3–32 KB (avg 8 KB). Area PB_Lob_Stmt | Always present; 3–32 KB (avg 8 KB). Area PB_Lob_Stmt |
| 12 | `StatementXml` | CLOB | – |  | Y | `?` (unknown) | Statement Xml | Always present; 1–8 KB (avg 3 KB). Area PB_Lob_Stmt | Always present; 1–8 KB (avg 3 KB). Area PB_Lob_Stmt |

## LOB fields

| Field | Type | Area | Max size | Codepage | Content | Populated | Min / Avg / Max bytes |
|---|---|---|---|---|---|---|---|
| `PdfContent` | BLOB | `PB_Lob_Stmt` | 32K | – | PDF | 100% | 3,072 / 8,192 / 32,768 |
| `StatementXml` | CLOB | `PB_Lob_Stmt` | 8K | UTF-8 | XML | 100% | 1,024 / 3,072 / 8,192 |

## Indexes

5 indexes (1 table-specific).

| Name | Components | Primary | Unique | Word | Purpose |
|---|---|---|---|---|---|
| `PkStatementDocument` *(std)* | StatementDocumentId ASC | Y | Y | N | Single-row random access by sequential ID; default scan order |
| `IxRandomInt10` *(std)* | RandomInt10 ASC, StatementDocumentId ASC | N | N | N | Select ≈ 10% of rows (RandomInt10 = k) |
| `IxRandomInt100` *(std)* | RandomInt100 ASC, StatementDocumentId ASC | N | N | N | Select ≈ 1% of rows (RandomInt100 = k) |
| `IxRandomInt1000` *(std)* | RandomInt1000 ASC, StatementDocumentId ASC | N | N | N | Select ≈ 0.1% of rows (RandomInt1000 = k) |
| `UxAccountStatement` | AccountStatementId ASC | N | Y | N | Fetch the document for a statement |

## Relationships

**Parents**

- `AccountStatementId` → [AccountStatement](AccountStatement.md).`AccountStatementId` — 0.008 / 0–1 children per parent

**Children**

- none

## Access examples

ABL: about 1% of rows, then one random existing row.

```abl
FOR EACH StatementDocument NO-LOCK WHERE StatementDocument.RandomInt100 = 42 USE-INDEX IxRandomInt100:
    /* work */
END.

DEFINE VARIABLE r AS INT64 NO-UNDO.
FIND BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.TableName = "StatementDocument".
r = RANDOM(1, INTEGER(BenchmarkTableInfo.MaxId)).
FIND StatementDocument NO-LOCK WHERE StatementDocument.StatementDocumentId = r NO-ERROR.   /* not AVAILABLE => draw again */
```

SQL:

```sql
SELECT * FROM PUB.StatementDocument WHERE RandomInt100 = 42;
SELECT MaxId FROM PUB.BenchmarkTableInfo WHERE TableName = 'StatementDocument';
SELECT * FROM PUB.StatementDocument WHERE StatementDocumentId = ?;   -- ? drawn uniformly from 1..MaxId
```
