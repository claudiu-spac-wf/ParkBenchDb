/*------------------------------------------------------------------------
    File        : db/abl/pbgen_counts.p
    Purpose     : Test helper for tests/test_pbgen_integration.py (spec 003 T027/T032).
    Usage       : _progres -b -db <db> -cpinternal UTF-8 -cpstream UTF-8
                      -p db/abl/pbgen_counts.p -param "<out-dir>|<sample-tables>"
    Output      : <out-dir>/counts.json:
                    {"tables": {"<table>": {"count": n, "maxId": n}, ...},
                     "sequences": {"<sequence>": value, ...},
                     "bti": {"<table>": {"MaxId": n, "TableRowCount": n}, ...}}
                  <out-dir>/sample-<table>.json for each comma-separated <sample-tables> entry:
                    the rows with RandomInt1000 = 1, sorted by ID (temp-table WRITE-JSON).
    Notes       : Counts every row of the 32 benchmark tables; Loader* tables are skipped.
  ----------------------------------------------------------------------*/

USING Progress.Json.ObjectModel.*.

DEFINE VARIABLE cOutDir  AS CHARACTER  NO-UNDO.
DEFINE VARIABLE cSamples AS CHARACTER  NO-UNDO.
DEFINE VARIABLE oOut     AS JsonObject NO-UNDO.
DEFINE VARIABLE oTables  AS JsonObject NO-UNDO.
DEFINE VARIABLE oSeqs    AS JsonObject NO-UNDO.
DEFINE VARIABLE oBti     AS JsonObject NO-UNDO.
DEFINE VARIABLE oOne     AS JsonObject NO-UNDO.
DEFINE VARIABLE iCount   AS INT64      NO-UNDO.
DEFINE VARIABLE iMax     AS INT64      NO-UNDO.
DEFINE VARIABLE i        AS INTEGER    NO-UNDO.
DEFINE VARIABLE hBuf     AS HANDLE     NO-UNDO.
DEFINE VARIABLE hQ       AS HANDLE     NO-UNDO.
DEFINE VARIABLE hTT      AS HANDLE     NO-UNDO.

ASSIGN
    cOutDir  = ENTRY(1, SESSION:PARAMETER, "|")
    cSamples = (IF NUM-ENTRIES(SESSION:PARAMETER, "|") > 1 THEN ENTRY(2, SESSION:PARAMETER, "|") ELSE "")
    oOut     = NEW JsonObject()
    oTables  = NEW JsonObject()
    oSeqs    = NEW JsonObject()
    oBti     = NEW JsonObject().

FOR EACH _File NO-LOCK WHERE _File._Tbl-Type = "T" AND NOT _File._File-Name BEGINS "Loader"
    BY _File._File-Name:
    ASSIGN iCount = 0 iMax = 0.
    CREATE BUFFER hBuf FOR TABLE _File._File-Name.
    CREATE QUERY hQ.
    hQ:SET-BUFFERS(hBuf).
    hQ:QUERY-PREPARE(SUBSTITUTE("FOR EACH &1 FIELDS(&1Id) NO-LOCK", _File._File-Name)).
    hQ:QUERY-OPEN().
    hQ:GET-FIRST().
    DO WHILE NOT hQ:QUERY-OFF-END:
        ASSIGN
            iCount = iCount + 1
            iMax   = MAXIMUM(iMax, hBuf:BUFFER-FIELD(_File._File-Name + "Id"):BUFFER-VALUE).
        hQ:GET-NEXT().
    END.
    hQ:QUERY-CLOSE().
    DELETE OBJECT hQ.
    DELETE OBJECT hBuf.
    oOne = NEW JsonObject().
    oOne:Add("count", iCount).
    oOne:Add("maxId", iMax).
    oTables:Add(_File._File-Name, oOne).
END.

FOR EACH _Sequence NO-LOCK:
    oSeqs:Add(_Sequence._Seq-Name, DYNAMIC-CURRENT-VALUE(_Sequence._Seq-Name, LDBNAME(1))).
END.

CREATE BUFFER hBuf FOR TABLE "BenchmarkTableInfo".
CREATE QUERY hQ.
hQ:SET-BUFFERS(hBuf).
hQ:QUERY-PREPARE("FOR EACH BenchmarkTableInfo NO-LOCK").
hQ:QUERY-OPEN().
hQ:GET-FIRST().
DO WHILE NOT hQ:QUERY-OFF-END:
    oOne = NEW JsonObject().
    oOne:Add("MaxId", INT64(hBuf:BUFFER-FIELD("MaxId"):BUFFER-VALUE)).
    oOne:Add("TableRowCount", INT64(hBuf:BUFFER-FIELD("TableRowCount"):BUFFER-VALUE)).
    oBti:Add(STRING(hBuf:BUFFER-FIELD("TableName"):BUFFER-VALUE), oOne).
    hQ:GET-NEXT().
END.
hQ:QUERY-CLOSE().
DELETE OBJECT hQ.
DELETE OBJECT hBuf.

oOut:Add("tables", oTables).
oOut:Add("sequences", oSeqs).
oOut:Add("bti", oBti).
oOut:WriteFile(cOutDir + "/counts.json", TRUE).

DO i = 1 TO NUM-ENTRIES(cSamples):
    CREATE TEMP-TABLE hTT.
    hTT:ADD-FIELDS-FROM(ENTRY(i, cSamples)).
    hTT:TEMP-TABLE-PREPARE(ENTRY(i, cSamples)).
    CREATE BUFFER hBuf FOR TABLE ENTRY(i, cSamples).
    CREATE QUERY hQ.
    hQ:SET-BUFFERS(hBuf).
    hQ:QUERY-PREPARE(SUBSTITUTE("FOR EACH &1 NO-LOCK WHERE &1.RandomInt1000 = 1 BY &1.&1Id", ENTRY(i, cSamples))).
    hQ:QUERY-OPEN().
    hQ:GET-FIRST().
    DO WHILE NOT hQ:QUERY-OFF-END:
        hTT:DEFAULT-BUFFER-HANDLE:BUFFER-CREATE().
        hTT:DEFAULT-BUFFER-HANDLE:BUFFER-COPY(hBuf).
        hQ:GET-NEXT().
    END.
    hQ:QUERY-CLOSE().
    hTT:WRITE-JSON("file", cOutDir + "/sample-" + ENTRY(i, cSamples) + ".json", TRUE, "UTF-8").
    DELETE OBJECT hQ.
    DELETE OBJECT hBuf.
    DELETE OBJECT hTT.
END.

QUIT.
