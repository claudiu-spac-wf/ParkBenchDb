/*------------------------------------------------------------------------
    File        : db/abl/verify_db.p
    Purpose     : Post-build verification for db/build_db.* (spec 002 FR-019).
    Usage       : _progres -b -1 -db <db> -cpinternal UTF-8 -cpstream UTF-8
                      -p db/abl/verify_db.p -param "<expect-file>|<status-file>[|<overrides>]"
    Output      : one "CHECK <name>: ok|FAIL (...)" line per check, then
                  "VERIFY OK" or "VERIFY FAILED (<n>)".
                  <status-file> gets "OK" or "FAILED: <n> check(s)".
    Notes       : The expect file (db/parkbench.expect) holds key=value lines produced by
                  tools/gen_db_files.py. Fields whose names or units could not be confirmed
                  without an OpenEdge install (research.md, marked ⚑) are read through
                  dynamic buffers, so a wrong name reports "FAIL (not readable)" instead
                  of stopping compilation of this procedure.
                  <overrides> (optional) is "key=value;key=value" and replaces expect-file
                  values, e.g. "biblocksize=8192;biclustersize=33554432" from --bi-block-size
                  and --bi-cluster-size (spec 003 FR-001).
  ----------------------------------------------------------------------*/

DEFINE TEMP-TABLE ttExpect NO-UNDO
    FIELD cKey   AS CHARACTER
    FIELD cValue AS CHARACTER
    INDEX ixKey IS PRIMARY UNIQUE cKey.

DEFINE VARIABLE cExpectFile AS CHARACTER NO-UNDO.
DEFINE VARIABLE cStatusFile AS CHARACTER NO-UNDO.
DEFINE VARIABLE cLine       AS CHARACTER NO-UNDO.
DEFINE VARIABLE iFailures   AS INTEGER   NO-UNDO.
DEFINE VARIABLE iTables     AS INTEGER   NO-UNDO.
DEFINE VARIABLE iFields     AS INTEGER   NO-UNDO.
DEFINE VARIABLE iIndexes    AS INTEGER   NO-UNDO.
DEFINE VARIABLE iDefaults   AS INTEGER   NO-UNDO.
DEFINE VARIABLE iSequences  AS INTEGER   NO-UNDO.
DEFINE VARIABLE cNames      AS CHARACTER NO-UNDO.
DEFINE VARIABLE cValue      AS CHARACTER NO-UNDO.
DEFINE VARIABLE cOverrides  AS CHARACTER NO-UNDO.
DEFINE VARIABLE iPair       AS INTEGER   NO-UNDO.

FUNCTION expected RETURNS CHARACTER (INPUT pcKey AS CHARACTER):
    FIND ttExpect WHERE ttExpect.cKey = pcKey NO-ERROR.
    RETURN (IF AVAILABLE ttExpect THEN ttExpect.cValue ELSE ?).
END FUNCTION.

/* Reads one field of the first record matching pcWhere in a (meta)table, or ? if unavailable. */
FUNCTION readField RETURNS CHARACTER (INPUT pcTable AS CHARACTER, INPUT pcWhere AS CHARACTER,
                                      INPUT pcField AS CHARACTER):
    DEFINE VARIABLE hBuffer AS HANDLE    NO-UNDO.
    DEFINE VARIABLE hField  AS HANDLE    NO-UNDO.
    DEFINE VARIABLE cResult AS CHARACTER NO-UNDO INITIAL ?.

    CREATE BUFFER hBuffer FOR TABLE pcTable NO-ERROR.
    IF NOT VALID-HANDLE(hBuffer) THEN RETURN ?.
    hBuffer:FIND-FIRST(pcWhere, NO-LOCK) NO-ERROR.
    IF hBuffer:AVAILABLE THEN DO:
        hField = hBuffer:BUFFER-FIELD(pcField) NO-ERROR.
        IF VALID-HANDLE(hField) AND hField:BUFFER-VALUE <> ? THEN
            cResult = STRING(hField:BUFFER-VALUE).
    END.
    DELETE OBJECT hBuffer.
    RETURN cResult.
END FUNCTION.

PROCEDURE check:
    DEFINE INPUT PARAMETER pcName     AS CHARACTER NO-UNDO.
    DEFINE INPUT PARAMETER pcExpected AS CHARACTER NO-UNDO.
    DEFINE INPUT PARAMETER pcFound    AS CHARACTER NO-UNDO.

    IF pcFound <> ? AND pcExpected <> ? AND pcFound = pcExpected THEN
        PUT UNFORMATTED "CHECK " pcName ": ok (" pcFound ")" SKIP.
    ELSE DO:
        iFailures = iFailures + 1.
        PUT UNFORMATTED "CHECK " pcName ": FAIL (expected "
            (IF pcExpected = ? THEN "?" ELSE pcExpected) ", found "
            (IF pcFound = ? THEN "not readable" ELSE pcFound) ")" SKIP.
    END.
END PROCEDURE.

/* Accepts a size reported either in bytes or in KB (the VST unit is unconfirmed, research R10). */
FUNCTION sizeInBytes RETURNS CHARACTER (INPUT pcRaw AS CHARACTER, INPUT pcExpected AS CHARACTER):
    IF pcRaw = ? OR pcExpected = ? THEN RETURN pcRaw.
    IF pcRaw = pcExpected THEN RETURN pcRaw.
    IF STRING(INT64(pcRaw) * 1024) = pcExpected THEN RETURN pcExpected.
    RETURN pcRaw.
END FUNCTION.

/* ---------------------------------------------------------------- read the expect file */
IF NUM-ENTRIES(SESSION:PARAMETER, "|") < 2 OR NUM-ENTRIES(SESSION:PARAMETER, "|") > 3 THEN DO:
    PUT UNFORMATTED "verify_db.p: -param must be ~"<expect-file>|<status-file>[|<overrides>]~"" SKIP.
    QUIT.
END.
ASSIGN
    cExpectFile = ENTRY(1, SESSION:PARAMETER, "|")
    cStatusFile = ENTRY(2, SESSION:PARAMETER, "|")
    cOverrides  = (IF NUM-ENTRIES(SESSION:PARAMETER, "|") = 3 THEN ENTRY(3, SESSION:PARAMETER, "|") ELSE "").

INPUT FROM VALUE(cExpectFile).
REPEAT:
    IMPORT UNFORMATTED cLine.
    IF INDEX(cLine, "=") = 0 THEN NEXT.
    CREATE ttExpect.
    ASSIGN
        ttExpect.cKey   = TRIM(SUBSTRING(cLine, 1, INDEX(cLine, "=") - 1))
        ttExpect.cValue = TRIM(SUBSTRING(cLine, INDEX(cLine, "=") + 1)).
END.
INPUT CLOSE.

DO iPair = 1 TO NUM-ENTRIES(cOverrides, ";"):
    cLine = ENTRY(iPair, cOverrides, ";").
    IF INDEX(cLine, "=") = 0 THEN NEXT.
    cValue = TRIM(SUBSTRING(cLine, 1, INDEX(cLine, "=") - 1)).
    FIND ttExpect WHERE ttExpect.cKey = cValue NO-ERROR.
    IF NOT AVAILABLE ttExpect THEN DO:
        CREATE ttExpect.
        ttExpect.cKey = cValue.
    END.
    ttExpect.cValue = TRIM(SUBSTRING(cLine, INDEX(cLine, "=") + 1)).
END.

/* ---------------------------------------------------------------- schema counts */
FOR EACH _File NO-LOCK WHERE _File._Tbl-Type = "T" BY _File._File-Name:
    ASSIGN
        iTables = iTables + 1
        cNames  = cNames + (IF cNames = "" THEN "" ELSE ",") + _File._File-Name.
    FOR EACH _Field NO-LOCK WHERE _Field._File-recid = RECID(_File):
        iFields = iFields + 1.
    END.
    FOR EACH _Index NO-LOCK WHERE _Index._File-recid = RECID(_File):
        iIndexes = iIndexes + 1.
        IF _Index._Index-Name = "default" THEN iDefaults = iDefaults + 1.
    END.
END.
FOR EACH _Sequence NO-LOCK:
    iSequences = iSequences + 1.
END.

RUN check ("tables",         expected("tables"),     STRING(iTables)).
RUN check ("table names",    expected("table-list"), cNames).
RUN check ("fields",         expected("fields"),     STRING(iFields)).
RUN check ("indexes",        expected("indexes"),    STRING(iIndexes)).
RUN check ("default indexes", "0",                   STRING(iDefaults)).
RUN check ("sequences",      expected("sequences"),  STRING(iSequences)).

/* ---------------------------------------------------------------- database settings */
FIND FIRST _Db NO-LOCK NO-ERROR.
RUN check ("codepage", expected("codepage"), (IF AVAILABLE _Db THEN _Db._Db-xl-name ELSE ?)).

RUN check ("block size", expected("blocksize"),
           readField("_Area", "WHERE _Area._Area-number = 6", "_Area-blocksize")).

cValue = readField("_Database-Feature", "WHERE _Database-Feature._DBFeature_Name = 'Large Files'",
                   "_DBFeature_Enabled").
RUN check ("large files", expected("largefiles"),
           (IF cValue = ? THEN ? ELSE IF cValue = "1" THEN "yes" ELSE "no")).

RUN check ("before-image block size", expected("biblocksize"),
           sizeInBytes(readField("_DbStatus", "", "_DbStatus-BiBlkSize"), expected("biblocksize"))).
RUN check ("before-image cluster size", expected("biclustersize"),
           sizeInBytes(readField("_DbStatus", "", "_DbStatus-BiClSize"), expected("biclustersize"))).

/* ---------------------------------------------------------------- result */
IF iFailures = 0 THEN PUT UNFORMATTED "VERIFY OK" SKIP.
ELSE PUT UNFORMATTED "VERIFY FAILED (" iFailures ")" SKIP.

OUTPUT TO VALUE(cStatusFile).
PUT UNFORMATTED (IF iFailures = 0 THEN "OK" ELSE "FAILED: " + STRING(iFailures) + " check(s)") SKIP.
OUTPUT CLOSE.

QUIT.
