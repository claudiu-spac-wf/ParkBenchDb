/*------------------------------------------------------------------------
    File        : db/abl/pbgen_init.p
    Purpose     : Creates the internal loader tables (LoaderRun, LoaderUnit) if they are missing.
    Usage       : _progres -b <connection> -cpinternal UTF-8 -cpstream UTF-8
                      -p db/abl/pbgen_init.p -param "<loader-df>|<status-file>"
    Result      : status file gets "OK created", "OK present" or "FAILED: <reason>".
                  Separate from pbgen_agent.p, which cannot compile until these tables exist.
  ----------------------------------------------------------------------*/
DEFINE VARIABLE cDf     AS CHARACTER NO-UNDO.
DEFINE VARIABLE cStatus AS CHARACTER NO-UNDO.
DEFINE VARIABLE cResult AS CHARACTER NO-UNDO.

ASSIGN
    cDf     = ENTRY(1, SESSION:PARAMETER, "|")
    cStatus = ENTRY(2, SESSION:PARAMETER, "|").

IF CAN-FIND(FIRST _File WHERE _File._File-Name = "LoaderUnit") THEN
    cResult = "OK present".
ELSE DO:
    OS-DELETE VALUE(LDBNAME(1) + ".e").
    DO ON ERROR UNDO, LEAVE:
        RUN prodict/load_df.p (INPUT cDf).
        CATCH eErr AS Progress.Lang.Error:
            cResult = "FAILED: " + eErr:GetMessage(1).
        END CATCH.
    END.
    FILE-INFO:FILE-NAME = LDBNAME(1) + ".e".
    IF cResult = "" AND FILE-INFO:FULL-PATHNAME <> ? AND FILE-INFO:FILE-SIZE > 0 THEN
        cResult = "FAILED: errors or warnings in " + FILE-INFO:FULL-PATHNAME.
    IF cResult = "" THEN
        cResult = IF CAN-FIND(FIRST _File WHERE _File._File-Name = "LoaderUnit") THEN "OK created"
                  ELSE "FAILED: LoaderUnit not found after load".
END.
OUTPUT TO VALUE(cStatus).
PUT UNFORMATTED cResult SKIP.
OUTPUT CLOSE.
QUIT.
