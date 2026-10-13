/*------------------------------------------------------------------------
    File        : db/abl/load_df.p
    Purpose     : Batch wrapper around the Data Dictionary loader for db/build_db.*.
    Usage       : _progres -b -1 -db <db> -cpinternal UTF-8 -cpstream UTF-8
                      -p db/abl/load_df.p -param "<df-file>|<status-file>"
    Result      : writes "OK" or "FAILED: <reason>" as the only line of <status-file>.
    Notes       : prodict/load_df.p takes the .df name as an INPUT parameter. It writes
                  errors AND warnings to <ldbname>.e in the working directory; any
                  non-empty .e file counts as a failure (spec 002, US1 scenario 2).
  ----------------------------------------------------------------------*/

DEFINE VARIABLE cDfFile     AS CHARACTER NO-UNDO.
DEFINE VARIABLE cStatusFile AS CHARACTER NO-UNDO.
DEFINE VARIABLE cErrFile    AS CHARACTER NO-UNDO.
DEFINE VARIABLE cResult     AS CHARACTER NO-UNDO INITIAL "OK".
DEFINE VARIABLE cLine       AS CHARACTER NO-UNDO.

IF NUM-ENTRIES(SESSION:PARAMETER, "|") <> 2 THEN DO:
    PUT UNFORMATTED "load_df.p: -param must be ~"<df-file>|<status-file>~"" SKIP.
    QUIT.
END.

ASSIGN
    cDfFile     = ENTRY(1, SESSION:PARAMETER, "|")
    cStatusFile = ENTRY(2, SESSION:PARAMETER, "|")
    cErrFile    = LDBNAME(1) + ".e".

/* Start from a clean error file so an old one cannot be mistaken for this run's output. */
OS-DELETE VALUE(cErrFile).

DO ON ERROR UNDO, LEAVE:
    RUN prodict/load_df.p (INPUT cDfFile).
    CATCH eErr AS Progress.Lang.Error:
        cResult = "FAILED: " + eErr:GetMessage(1).
    END CATCH.
END.

FILE-INFO:FILE-NAME = cErrFile.
IF FILE-INFO:FULL-PATHNAME <> ? AND FILE-INFO:FILE-SIZE > 0 THEN DO:
    IF cResult = "OK" THEN
        cResult = "FAILED: errors or warnings reported in " + FILE-INFO:FULL-PATHNAME.
    PUT UNFORMATTED "---- " FILE-INFO:FULL-PATHNAME " ----" SKIP.
    INPUT FROM VALUE(FILE-INFO:FULL-PATHNAME).
    REPEAT:
        IMPORT UNFORMATTED cLine.
        PUT UNFORMATTED cLine SKIP.
    END.
    INPUT CLOSE.
END.

PUT UNFORMATTED "load_df: " cResult SKIP.

OUTPUT TO VALUE(cStatusFile).
PUT UNFORMATTED cResult SKIP.
OUTPUT CLOSE.

QUIT.
