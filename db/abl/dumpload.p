/*------------------------------------------------------------------------
    File        : db/abl/dumpload.p
    Purpose     : The ABL half of db/dump_db.* and db/load_db.* (binary dump and load between OSs).
    Usage       : _progres -b -db <db> -cpinternal UTF-8 -cpstream UTF-8 -p db/abl/dumpload.p
                      -param "dump|<dump-dir>"                  (source database)
                      -param "finish|<dump-dir>|<status-file>"  (target, after load and idxbuild)
    dump        : writes <dump-dir>/schema.df (prodict/dump_df.p, all tables and sequences) and
                  <dump-dir>/manifest.txt with one line per item:
                      format=parkbench-dump-1
                      source=<physical db name>   created=<ISO time>   openedge=<PROVERSION>
                      codepage=<db codepage>
                      table=<name>                 (every application table, Loader* included)
                      seq=<name>=<current value>   (proutil binary dumps don't carry sequences)
                  The dump scripts append rows=<table>=<n> lines from proutil's own counts.
    finish      : sets every sequence from manifest.txt, then checks: the same tables exist, every
                  sequence reads back its value, and no index is inactive. Prints CHECK lines and
                  writes "OK" or "FAILED: <n> check(s)" to <status-file>.
  ----------------------------------------------------------------------*/

DEFINE VARIABLE cMode    AS CHARACTER NO-UNDO.
DEFINE VARIABLE cDir     AS CHARACTER NO-UNDO.
DEFINE VARIABLE cStatus  AS CHARACTER NO-UNDO.
DEFINE VARIABLE cLine    AS CHARACTER NO-UNDO.
DEFINE VARIABLE cName    AS CHARACTER NO-UNDO.
DEFINE VARIABLE cWanted  AS CHARACTER NO-UNDO.
DEFINE VARIABLE cHave    AS CHARACTER NO-UNDO.
DEFINE VARIABLE iValue   AS INT64     NO-UNDO.
DEFINE VARIABLE iFail    AS INTEGER   NO-UNDO.
DEFINE VARIABLE iSeqs    AS INTEGER   NO-UNDO.
DEFINE VARIABLE iBadSeq  AS INTEGER   NO-UNDO.
DEFINE VARIABLE iInactive AS INTEGER  NO-UNDO.

ASSIGN
    cMode = ENTRY(1, SESSION:PARAMETER, "|")
    cDir  = ENTRY(2, SESSION:PARAMETER, "|").

PROCEDURE check:
    DEFINE INPUT PARAMETER pcName AS CHARACTER NO-UNDO.
    DEFINE INPUT PARAMETER plOk   AS LOGICAL   NO-UNDO.
    DEFINE INPUT PARAMETER pcInfo AS CHARACTER NO-UNDO.
    PUT UNFORMATTED "CHECK " pcName ": " (IF plOk THEN "ok" ELSE "FAIL") " (" pcInfo ")" SKIP.
    IF NOT plOk THEN iFail = iFail + 1.
END PROCEDURE.

IF cMode = "dump" THEN DO:
    RUN prodict/dump_df.p (INPUT "ALL", INPUT cDir + "/schema.df", INPUT "").
    FIND FIRST _Db NO-LOCK.
    OUTPUT TO VALUE(cDir + "/manifest.txt").
    PUT UNFORMATTED "format=parkbench-dump-1" SKIP
                    "source=" PDBNAME(1) SKIP
                    "created=" ISO-DATE(NOW) SKIP
                    "openedge=" PROVERSION SKIP
                    "codepage=" _Db._Db-xl-name SKIP.
    FOR EACH _File NO-LOCK WHERE _File._Tbl-Type = "T" BY _File._File-Name:
        PUT UNFORMATTED "table=" _File._File-Name SKIP.
    END.
    /* pbgen units claimed by running workers: the dump scripts refuse, since the data is still changing */
    iValue = 0.
    IF CAN-FIND(_File WHERE _File._File-Name = "LoaderUnit") THEN DO:
        DEFINE VARIABLE hBuf AS HANDLE NO-UNDO.
        DEFINE VARIABLE hQ   AS HANDLE NO-UNDO.
        CREATE BUFFER hBuf FOR TABLE "LoaderUnit".
        CREATE QUERY hQ.
        hQ:SET-BUFFERS(hBuf).
        hQ:QUERY-PREPARE("FOR EACH LoaderUnit NO-LOCK WHERE LoaderUnit.UnitStatus = 'C'").
        hQ:QUERY-OPEN().
        hQ:GET-FIRST().
        DO WHILE NOT hQ:QUERY-OFF-END:
            iValue = iValue + 1.
            hQ:GET-NEXT().
        END.
        DELETE OBJECT hQ.
        DELETE OBJECT hBuf.
    END.
    PUT UNFORMATTED "activeClaims=" iValue SKIP.
    FOR EACH _Sequence NO-LOCK BY _Sequence._Seq-Name:
        PUT UNFORMATTED "seq=" _Sequence._Seq-Name "=" DYNAMIC-CURRENT-VALUE(_Sequence._Seq-Name, LDBNAME(1)) SKIP.
    END.
    OUTPUT CLOSE.
    PUT UNFORMATTED "DUMPINFO OK" SKIP.
    QUIT.
END.

IF cMode <> "finish" THEN DO:
    PUT UNFORMATTED "dumpload.p: mode must be dump or finish" SKIP.
    QUIT.
END.

cStatus = ENTRY(3, SESSION:PARAMETER, "|").
INPUT FROM VALUE(cDir + "/manifest.txt").
REPEAT:
    IMPORT UNFORMATTED cLine.
    IF cLine BEGINS "table=" THEN
        cWanted = cWanted + (IF cWanted = "" THEN "" ELSE ",") + SUBSTRING(cLine, 7).
    ELSE IF cLine BEGINS "seq=" THEN DO:
        ASSIGN
            cName  = ENTRY(2, cLine, "=")
            iValue = INT64(ENTRY(3, cLine, "="))
            iSeqs  = iSeqs + 1.
        DYNAMIC-CURRENT-VALUE(cName, LDBNAME(1)) = iValue NO-ERROR.
        IF ERROR-STATUS:ERROR OR DYNAMIC-CURRENT-VALUE(cName, LDBNAME(1)) <> iValue THEN DO:
            iBadSeq = iBadSeq + 1.
            PUT UNFORMATTED "sequence " cName " could not be set to " iValue SKIP.
        END.
    END.
END.
INPUT CLOSE.

FOR EACH _File NO-LOCK WHERE _File._Tbl-Type = "T" BY _File._File-Name:
    cHave = cHave + (IF cHave = "" THEN "" ELSE ",") + _File._File-Name.
    FOR EACH _Index NO-LOCK WHERE _Index._File-recid = RECID(_File) AND NOT _Index._Active:
        iInactive = iInactive + 1.
        PUT UNFORMATTED "inactive index " _File._File-Name "." _Index._Index-Name SKIP.
    END.
END.

RUN check ("tables", cHave = cWanted, STRING(NUM-ENTRIES(cHave)) + " tables").
RUN check ("sequences", iBadSeq = 0, STRING(iSeqs) + " set from the dump" + (IF iBadSeq > 0 THEN ", " + STRING(iBadSeq) + " failed" ELSE "")).
RUN check ("indexes active", iInactive = 0, STRING(iInactive) + " inactive").

PUT UNFORMATTED (IF iFail = 0 THEN "FINISH OK" ELSE "FINISH FAILED (" + STRING(iFail) + ")") SKIP.
OUTPUT TO VALUE(cStatus).
PUT UNFORMATTED (IF iFail = 0 THEN "OK" ELSE "FAILED: " + STRING(iFail) + " check(s)") SKIP.
OUTPUT CLOSE.
QUIT.
