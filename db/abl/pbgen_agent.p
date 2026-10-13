/*------------------------------------------------------------------------
    File        : db/abl/pbgen_agent.p
    Purpose     : Persistent database agent for the pbgen data generator (feature 003).
                  One agent per worker; it owns all database access for that worker.
    Usage       : _progres -b <connection> -cpinternal UTF-8 -cpstream UTF-8
                      -p db/abl/pbgen_agent.p -param "<spool-dir>"
    Protocol    : Python writes <spool>/req-<n>.json (atomically); the agent answers with
                  <spool>/resp-<n>.json. n starts at 1. One JSON object each way.
                  See specs/003-data-generation/data-model.md §4.
    Ops         : hello quit plan state claim heartbeat load watermark finalize release status sample
    Notes       : A unit is loaded, and marked done, in ONE transaction, so a killed worker never
                  leaves partial data. The agent exits after 10 minutes without requests.
  ----------------------------------------------------------------------*/

USING Progress.Json.ObjectModel.*.

DEFINE VARIABLE cSpool      AS CHARACTER         NO-UNDO.
DEFINE VARIABLE iSeq        AS INTEGER           NO-UNDO INITIAL 1.
DEFINE VARIABLE cReqFile    AS CHARACTER         NO-UNDO.
DEFINE VARIABLE iIdleMs     AS INT64             NO-UNDO.
DEFINE VARIABLE oParser     AS ObjectModelParser NO-UNDO.
DEFINE VARIABLE oReq        AS JsonObject        NO-UNDO.
DEFINE VARIABLE oResp       AS JsonObject        NO-UNDO.
DEFINE VARIABLE lQuit       AS LOGICAL           NO-UNDO.
DEFINE VARIABLE hUnitDs     AS HANDLE            NO-UNDO.
DEFINE VARIABLE cDataTables AS CHARACTER         NO-UNDO.

&SCOPED-DEFINE IDLE_LIMIT_MS 600000
&SCOPED-DEFINE STALE_SECONDS 300

/* NOTE: every buffer that takes a lock is defined inside the procedure that uses it, so its record
   locks end with the procedure. File-scoped buffers keep a SHARE lock after the transaction and
   block other agents' EXCLUSIVE finds (a multi-worker deadlock found in testing). */

DEFINE TEMP-TABLE ttMax NO-UNDO
    FIELD cTable AS CHARACTER
    FIELD iMax   AS INT64
    INDEX ixT IS PRIMARY UNIQUE cTable.

/* ====================================================================== helpers */

FUNCTION reqChar RETURNS CHARACTER (INPUT pcKey AS CHARACTER):
    IF oReq:Has(pcKey) AND NOT oReq:IsNull(pcKey) THEN RETURN oReq:GetCharacter(pcKey).
    RETURN ?.
END FUNCTION.

FUNCTION reqInt64 RETURNS INT64 (INPUT pcKey AS CHARACTER):
    IF oReq:Has(pcKey) AND NOT oReq:IsNull(pcKey) THEN RETURN oReq:GetInt64(pcKey).
    RETURN ?.
END FUNCTION.

/* "Table=value;Table=value" -> value for pcTable, or ? */
FUNCTION mapValue RETURNS INT64 (INPUT pcMap AS CHARACTER, INPUT pcTable AS CHARACTER):
    DEFINE VARIABLE i AS INTEGER NO-UNDO.
    DO i = 1 TO NUM-ENTRIES(pcMap, ";"):
        IF ENTRY(1, ENTRY(i, pcMap, ";"), "=") = pcTable THEN
            RETURN INT64(ENTRY(2, ENTRY(i, pcMap, ";"), "=")).
    END.
    RETURN ?.
END FUNCTION.

FUNCTION unitJson RETURNS JsonObject (BUFFER pUnit FOR LoaderUnit):
    DEFINE VARIABLE o AS JsonObject NO-UNDO.
    o = NEW JsonObject().
    o:Add("LoaderRunId", pUnit.LoaderRunId).
    o:Add("UnitNo", pUnit.UnitNo).
    o:Add("Phase", pUnit.Phase).
    o:Add("UnitKind", pUnit.UnitKind).
    o:Add("UnitStatus", pUnit.UnitStatus).
    o:Add("UnitSeed", pUnit.UnitSeed).
    o:Add("FirstIds", pUnit.FirstIds).
    o:Add("RowCounts", pUnit.RowCounts).
    o:Add("TotalRows", pUnit.TotalRows).
    o:Add("ClaimedBy", pUnit.ClaimedBy).
    o:Add("Attempts", pUnit.Attempts).
    RETURN o.
END FUNCTION.

/* Reads one field of the first record matching pcWhere, or ? (for VST fields whose names vary). */
FUNCTION readField RETURNS CHARACTER (INPUT pcTable AS CHARACTER, INPUT pcWhere AS CHARACTER,
                                      INPUT pcField AS CHARACTER):
    DEFINE VARIABLE hB AS HANDLE    NO-UNDO.
    DEFINE VARIABLE hF AS HANDLE    NO-UNDO.
    DEFINE VARIABLE c  AS CHARACTER NO-UNDO INITIAL ?.
    CREATE BUFFER hB FOR TABLE pcTable NO-ERROR.
    IF NOT VALID-HANDLE(hB) THEN RETURN ?.
    hB:FIND-FIRST(pcWhere, NO-LOCK) NO-ERROR.
    IF hB:AVAILABLE THEN DO:
        hF = hB:BUFFER-FIELD(pcField) NO-ERROR.
        IF VALID-HANDLE(hF) AND hF:BUFFER-VALUE <> ? THEN c = STRING(hF:BUFFER-VALUE).
    END.
    DELETE OBJECT hB.
    RETURN c.
END FUNCTION.

FUNCTION dataFile RETURNS CHARACTER ():
    RETURN cSpool + "/data-" + STRING(iSeq) + ".json".
END FUNCTION.

/* Builds the dataset used to read unit files: one temp-table per benchmark table (fields only). */
PROCEDURE buildUnitDataset:
    DEFINE VARIABLE hTT AS HANDLE NO-UNDO.
    CREATE DATASET hUnitDs.
    hUnitDs:NAME = "unit".
    FOR EACH _File NO-LOCK WHERE _File._Tbl-Type = "T" AND NOT _File._File-Name BEGINS "Loader"
        BY _File._File-Name:
        CREATE TEMP-TABLE hTT.
        hTT:ADD-FIELDS-FROM(_File._File-Name).
        hTT:TEMP-TABLE-PREPARE(_File._File-Name).
        hUnitDs:ADD-BUFFER(hTT:DEFAULT-BUFFER-HANDLE).
        cDataTables = cDataTables + (IF cDataTables = "" THEN "" ELSE ",") + _File._File-Name.
    END.
END PROCEDURE.

/* Copies every row of temp-table buffer phTT into a new database buffer; returns the count. */
FUNCTION copyRows RETURNS INT64 (INPUT phTT AS HANDLE, INPUT pcTable AS CHARACTER):
    DEFINE VARIABLE hDb AS HANDLE NO-UNDO.
    DEFINE VARIABLE hQ  AS HANDLE NO-UNDO.
    DEFINE VARIABLE n   AS INT64  NO-UNDO.
    CREATE BUFFER hDb FOR TABLE pcTable.
    CREATE QUERY hQ.
    hQ:SET-BUFFERS(phTT).
    hQ:QUERY-PREPARE("FOR EACH " + phTT:NAME).
    hQ:QUERY-OPEN().
    hQ:GET-FIRST().
    DO WHILE NOT hQ:QUERY-OFF-END:
        hDb:BUFFER-CREATE().
        hDb:BUFFER-COPY(phTT).
        hDb:BUFFER-RELEASE().
        n = n + 1.
        hQ:GET-NEXT().
    END.
    hQ:QUERY-CLOSE().
    DELETE OBJECT hQ.
    DELETE OBJECT hDb.
    RETURN n.
END FUNCTION.

/* Writes the rows of a database table matching pcWhere to a JSON file (array of objects). */
PROCEDURE dumpRows:
    DEFINE INPUT PARAMETER pcTable AS CHARACTER NO-UNDO.
    DEFINE INPUT PARAMETER pcWhere AS CHARACTER NO-UNDO.
    DEFINE INPUT PARAMETER pcFile  AS CHARACTER NO-UNDO.
    DEFINE OUTPUT PARAMETER piRows AS INT64     NO-UNDO.
    DEFINE VARIABLE hTT AS HANDLE NO-UNDO.
    DEFINE VARIABLE hDb AS HANDLE NO-UNDO.
    DEFINE VARIABLE hQ  AS HANDLE NO-UNDO.
    CREATE TEMP-TABLE hTT.
    hTT:ADD-FIELDS-FROM(pcTable).
    hTT:TEMP-TABLE-PREPARE(pcTable).
    CREATE BUFFER hDb FOR TABLE pcTable.
    CREATE QUERY hQ.
    hQ:SET-BUFFERS(hDb).
    hQ:QUERY-PREPARE("FOR EACH " + pcTable + " NO-LOCK " + pcWhere).
    hQ:QUERY-OPEN().
    hQ:GET-FIRST().
    DO WHILE NOT hQ:QUERY-OFF-END:
        hTT:DEFAULT-BUFFER-HANDLE:BUFFER-CREATE().
        hTT:DEFAULT-BUFFER-HANDLE:BUFFER-COPY(hDb).
        piRows = piRows + 1.
        hQ:GET-NEXT().
    END.
    hQ:QUERY-CLOSE().
    hTT:WRITE-JSON("file", pcFile, FALSE, "UTF-8", FALSE, TRUE).
    DELETE OBJECT hQ.
    DELETE OBJECT hDb.
    DELETE OBJECT hTT.
END PROCEDURE.

/* ====================================================================== ops */

PROCEDURE opHello:
    DEFINE VARIABLE cL AS CHARACTER NO-UNDO.
    cL = readField("_DbParams", "WHERE _DbParams._DbParams-Name = '-L'", "_DbParams-Value").  /* server lock table size */
    oResp:Add("db", LDBNAME(1)).
    oResp:Add("version", "0.1.0").
    oResp:Add("loaderTables", CAN-FIND(FIRST _File WHERE _File._File-Name = "LoaderUnit")).
    oResp:Add("tables", NUM-ENTRIES(cDataTables)).
    IF cL = ? THEN oResp:AddNull("L"). ELSE oResp:Add("L", INT64(cL)).
END PROCEDURE.

/* Inserts a planned run and its units in one transaction. File: {"LoaderRun":[..],"LoaderUnit":[..]} */
PROCEDURE opPlan:
    DEFINE VARIABLE hDs  AS HANDLE NO-UNDO.
    DEFINE VARIABLE hRun AS HANDLE NO-UNDO.
    DEFINE VARIABLE hUn  AS HANDLE NO-UNDO.
    DEFINE VARIABLE n    AS INT64  NO-UNDO.
    CREATE TEMP-TABLE hRun.
    hRun:ADD-FIELDS-FROM("LoaderRun").
    hRun:TEMP-TABLE-PREPARE("LoaderRun").
    CREATE TEMP-TABLE hUn.
    hUn:ADD-FIELDS-FROM("LoaderUnit").
    hUn:TEMP-TABLE-PREPARE("LoaderUnit").
    CREATE DATASET hDs.
    hDs:ADD-BUFFER(hRun:DEFAULT-BUFFER-HANDLE).
    hDs:ADD-BUFFER(hUn:DEFAULT-BUFFER-HANDLE).
    hDs:READ-JSON("file", reqChar("file"), "EMPTY").
    hRun:DEFAULT-BUFFER-HANDLE:FIND-FIRST().
    IF CAN-FIND(FIRST LoaderRun WHERE LoaderRun.LoaderRunId =
                INT64(hRun:DEFAULT-BUFFER-HANDLE:BUFFER-FIELD("LoaderRunId"):BUFFER-VALUE)) THEN
        UNDO, THROW NEW Progress.Lang.AppError("run already exists", 1).
    IF CAN-FIND(FIRST LoaderRun WHERE LoaderRun.RunStatus <> "COMPLETE") THEN
        UNDO, THROW NEW Progress.Lang.AppError("another run is not complete", 1).
    DO TRANSACTION:
        n = copyRows(hRun:DEFAULT-BUFFER-HANDLE, "LoaderRun").
        n = n + copyRows(hUn:DEFAULT-BUFFER-HANDLE, "LoaderUnit").
    END.
    oResp:Add("rows", n).
    DELETE OBJECT hDs.
    DELETE OBJECT hRun.
    DELETE OBJECT hUn.
END PROCEDURE.

/* LoaderRun rows and BenchmarkTableInfo rows, written to data files. */
PROCEDURE opState:
    DEFINE VARIABLE cFile AS CHARACTER NO-UNDO.
    DEFINE VARIABLE n     AS INT64     NO-UNDO.
    cFile = dataFile().
    RUN dumpRows ("LoaderRun", "BY LoaderRun.LoaderRunId", cFile + ".runs", OUTPUT n).
    RUN dumpRows ("BenchmarkTableInfo", "BY BenchmarkTableInfo.TableName", cFile + ".bti", OUTPUT n).
    oResp:Add("runsFile", cFile + ".runs").
    oResp:Add("btiFile", cFile + ".bti").
END PROCEDURE.

/* Claims the lowest pending (or stale-claimed) unit of the lowest open phase of the open run. */
PROCEDURE opClaim:
    DEFINE BUFFER bUnit FOR LoaderUnit.
    DEFINE BUFFER bRun  FOR LoaderRun.
    DEFINE VARIABLE cWorker AS CHARACTER   NO-UNDO.
    DEFINE VARIABLE iRun    AS INT64       NO-UNDO.
    DEFINE VARIABLE iPhase  AS INTEGER     NO-UNDO INITIAL ?.
    DEFINE VARIABLE p       AS INTEGER     NO-UNDO.
    DEFINE VARIABLE tStale  AS DATETIME-TZ NO-UNDO.
    DEFINE VARIABLE rFound  AS ROWID       NO-UNDO.
    cWorker = reqChar("worker").
    tStale  = ADD-INTERVAL(NOW, - {&STALE_SECONDS}, "seconds").

    FIND FIRST LoaderRun NO-LOCK WHERE LoaderRun.RunStatus <> "COMPLETE" NO-ERROR.
    IF NOT AVAILABLE LoaderRun THEN DO:
        oResp:AddNull("unit").
        oResp:Add("reason", IF CAN-FIND(FIRST LoaderRun) THEN "run-complete" ELSE "no-run").
        RETURN.
    END.
    iRun = LoaderRun.LoaderRunId.

    DO p = 0 TO 2:
        IF CAN-FIND(FIRST LoaderUnit WHERE LoaderUnit.LoaderRunId = iRun AND LoaderUnit.Phase = p
                    AND LoaderUnit.UnitStatus = "P")
           OR CAN-FIND(FIRST LoaderUnit WHERE LoaderUnit.LoaderRunId = iRun AND LoaderUnit.Phase = p
                    AND LoaderUnit.UnitStatus = "C") THEN DO:
            iPhase = p.
            LEAVE.
        END.
    END.
    IF iPhase = ? THEN DO:
        oResp:AddNull("unit").
        oResp:Add("reason", "run-complete").
        RETURN.
    END.

    claimBlock:
    DO TRANSACTION:
        FOR EACH LoaderUnit NO-LOCK WHERE LoaderUnit.LoaderRunId = iRun AND LoaderUnit.Phase = iPhase
            AND (LoaderUnit.UnitStatus = "P"
                 OR (LoaderUnit.UnitStatus = "C" AND LoaderUnit.HeartbeatAt < tStale))
            BY LoaderUnit.UnitNo:
            FIND bUnit WHERE ROWID(bUnit) = ROWID(LoaderUnit) EXCLUSIVE-LOCK NO-WAIT NO-ERROR.
            IF LOCKED bUnit OR NOT AVAILABLE bUnit THEN NEXT.
            IF NOT (bUnit.UnitStatus = "P" OR (bUnit.UnitStatus = "C" AND bUnit.HeartbeatAt < tStale)) THEN DO:
                RELEASE bUnit.
                NEXT.
            END.
            ASSIGN
                bUnit.UnitStatus  = "C"
                bUnit.ClaimedBy   = cWorker
                bUnit.ClaimedAt   = NOW
                bUnit.HeartbeatAt = NOW
                bUnit.Attempts    = bUnit.Attempts + 1.
            rFound = ROWID(bUnit).
            LEAVE.
        END.
    END.
    IF rFound = ? THEN DO:
        oResp:AddNull("unit").
        oResp:Add("reason", "phase-blocked").
        RETURN.
    END.
    RELEASE bUnit.
    FIND bUnit WHERE ROWID(bUnit) = rFound NO-LOCK.
    oResp:Add("unit", unitJson(BUFFER bUnit)).

    IF LoaderRun.RunStatus = "PLANNED" THEN DO TRANSACTION:
        FIND bRun WHERE ROWID(bRun) = ROWID(LoaderRun) EXCLUSIVE-LOCK NO-WAIT NO-ERROR.
        IF AVAILABLE bRun AND bRun.RunStatus = "PLANNED" THEN bRun.RunStatus = "RUNNING".
    END.
    RELEASE bRun.
END PROCEDURE.

PROCEDURE opHeartbeat:
    DEFINE BUFFER bUnit FOR LoaderUnit.
    DEFINE BUFFER bRun  FOR LoaderRun.
    DO TRANSACTION:
        FIND bUnit WHERE bUnit.LoaderRunId = reqInt64("run") AND bUnit.UnitNo = INTEGER(reqInt64("unitNo"))
            EXCLUSIVE-LOCK NO-ERROR.
        IF NOT AVAILABLE bUnit OR bUnit.UnitStatus <> "C" OR bUnit.ClaimedBy <> reqChar("worker") THEN
            UNDO, THROW NEW Progress.Lang.AppError("lost", 1).
        bUnit.HeartbeatAt = NOW.
    END.
    RELEASE bUnit.
END PROCEDURE.

/* Loads a unit file and marks the unit done, all in one transaction. */
PROCEDURE opLoad:
    DEFINE BUFFER bUnit FOR LoaderUnit.
    DEFINE BUFFER bRun  FOR LoaderRun.
    DEFINE VARIABLE iRows   AS INT64  NO-UNDO.
    DEFINE VARIABLE i       AS INTEGER NO-UNDO.
    DEFINE VARIABLE hBuf    AS HANDLE NO-UNDO.
    DEFINE VARIABLE iStart  AS INT64  NO-UNDO.
    DEFINE VARIABLE lLost   AS LOGICAL NO-UNDO.
    iStart = ETIME.
    DO i = 1 TO hUnitDs:NUM-BUFFERS:
        hUnitDs:GET-BUFFER-HANDLE(i):EMPTY-TEMP-TABLE().
    END.
    hUnitDs:READ-JSON("file", reqChar("file"), "EMPTY").

    loadBlock:
    DO TRANSACTION ON ERROR UNDO, THROW:
        FIND bUnit WHERE bUnit.LoaderRunId = reqInt64("run") AND bUnit.UnitNo = INTEGER(reqInt64("unitNo"))
            EXCLUSIVE-LOCK.
        IF bUnit.UnitStatus <> "C" OR bUnit.ClaimedBy <> reqChar("worker") THEN DO:
            lLost = TRUE.
            UNDO loadBlock, LEAVE loadBlock.
        END.
        DO i = 1 TO hUnitDs:NUM-BUFFERS:
            hBuf = hUnitDs:GET-BUFFER-HANDLE(i).
            iRows = iRows + copyRows(hBuf, hBuf:TABLE).
        END.
        IF iRows <> bUnit.TotalRows THEN
            UNDO, THROW NEW Progress.Lang.AppError(SUBSTITUTE("unit &1 has &2 rows, expected &3",
                bUnit.UnitNo, iRows, bUnit.TotalRows), 1).
        ASSIGN
            bUnit.UnitStatus = "D"
            bUnit.DoneAt     = NOW.
    END.
    DO i = 1 TO hUnitDs:NUM-BUFFERS:
        hUnitDs:GET-BUFFER-HANDLE(i):EMPTY-TEMP-TABLE().
    END.
    RELEASE bUnit.
    IF lLost THEN UNDO, THROW NEW Progress.Lang.AppError("lost", 1).
    oResp:Add("rows", iRows).
    oResp:Add("ms", ETIME - iStart).
END PROCEDURE.

/* Advances BenchmarkTableInfo over the longest prefix of done units (incrementally). */
PROCEDURE opWatermark:
    DEFINE BUFFER bUnit FOR LoaderUnit.
    DEFINE BUFFER bRun  FOR LoaderRun.
    DEFINE VARIABLE iRun  AS INT64     NO-UNDO.
    DEFINE VARIABLE iPos  AS INTEGER   NO-UNDO.
    DEFINE VARIABLE i     AS INTEGER   NO-UNDO.
    DEFINE VARIABLE cT    AS CHARACTER NO-UNDO.
    DEFINE VARIABLE iEnd  AS INT64     NO-UNDO.
    iRun = reqInt64("run").
    EMPTY TEMP-TABLE ttMax.
    DO TRANSACTION:
        FIND bRun WHERE bRun.LoaderRunId = iRun EXCLUSIVE-LOCK.
        iPos = bRun.UnitsDone.
        FOR EACH LoaderUnit NO-LOCK WHERE LoaderUnit.LoaderRunId = iRun AND LoaderUnit.UnitNo > iPos
            BY LoaderUnit.UnitNo:
            IF LoaderUnit.UnitStatus <> "D" THEN LEAVE.
            iPos = LoaderUnit.UnitNo.
            DO i = 1 TO NUM-ENTRIES(LoaderUnit.RowCounts, ";"):
                cT = ENTRY(1, ENTRY(i, LoaderUnit.RowCounts, ";"), "=").
                iEnd = mapValue(LoaderUnit.FirstIds, cT) + INT64(ENTRY(2, ENTRY(i, LoaderUnit.RowCounts, ";"), "=")) - 1.
                FIND ttMax WHERE ttMax.cTable = cT NO-ERROR.
                IF NOT AVAILABLE ttMax THEN DO:
                    CREATE ttMax.
                    ttMax.cTable = cT.
                END.
                IF iEnd > ttMax.iMax THEN ttMax.iMax = iEnd.
            END.
        END.
        IF iPos > bRun.UnitsDone THEN DO:
            FOR EACH ttMax:
                FIND BenchmarkTableInfo WHERE BenchmarkTableInfo.TableName = ttMax.cTable EXCLUSIVE-LOCK NO-ERROR.
                IF AVAILABLE BenchmarkTableInfo AND ttMax.iMax > BenchmarkTableInfo.MaxId THEN
                    ASSIGN
                        BenchmarkTableInfo.MaxId         = ttMax.iMax
                        BenchmarkTableInfo.TableRowCount = ttMax.iMax
                        BenchmarkTableInfo.LoadedAt      = NOW.
            END.
            bRun.UnitsDone = iPos.
        END.
        oResp:Add("unitsDone", bRun.UnitsDone).
        oResp:Add("unitCount", bRun.UnitCount).
        oResp:Add("complete", bRun.UnitsDone >= bRun.UnitCount).
    END.
    RELEASE bRun.
    RELEASE BenchmarkTableInfo.
END PROCEDURE.

/* Sets sequences to MaxId and marks the run complete (idempotent). */
PROCEDURE opFinalize:
    DEFINE BUFFER bUnit FOR LoaderUnit.
    DEFINE BUFFER bRun  FOR LoaderRun.
    DEFINE VARIABLE iRun AS INT64 NO-UNDO.
    iRun = reqInt64("run").
    DO TRANSACTION:
        FIND bRun WHERE bRun.LoaderRunId = iRun EXCLUSIVE-LOCK.
        IF bRun.UnitsDone < bRun.UnitCount THEN
            UNDO, THROW NEW Progress.Lang.AppError("run is not complete", 1).
        FOR EACH BenchmarkTableInfo EXCLUSIVE-LOCK:
            DYNAMIC-CURRENT-VALUE("Seq" + BenchmarkTableInfo.TableName + "Id", LDBNAME(1)) = BenchmarkTableInfo.MaxId.
            BenchmarkTableInfo.ScaleFactor = ROUND(bRun.TargetScale, 2).
        END.
        IF bRun.RunStatus <> "COMPLETE" THEN
            ASSIGN
                bRun.RunStatus         = "COMPLETE"
                bRun.CompletedAt       = NOW
                bRun.MeasuredDiskBytes = (IF reqInt64("diskBytes") = ? THEN 0 ELSE reqInt64("diskBytes")).
        oResp:Add("status", bRun.RunStatus).
    END.
    RELEASE bRun.
    RELEASE BenchmarkTableInfo.
END PROCEDURE.

/* Releases claims back to pending: {"run":r, "workers":[...]} and/or {"olderThanSec":n}. */
PROCEDURE opRelease:
    DEFINE BUFFER bUnit FOR LoaderUnit.
    DEFINE BUFFER bRun  FOR LoaderRun.
    DEFINE VARIABLE oWorkers AS JsonArray   NO-UNDO.
    DEFINE VARIABLE cList    AS CHARACTER   NO-UNDO.
    DEFINE VARIABLE i        AS INTEGER     NO-UNDO.
    DEFINE VARIABLE tOld     AS DATETIME-TZ NO-UNDO.
    DEFINE VARIABLE n        AS INTEGER     NO-UNDO.
    IF oReq:Has("workers") THEN DO:
        oWorkers = oReq:GetJsonArray("workers").
        DO i = 1 TO oWorkers:Length:
            cList = cList + CHR(1) + oWorkers:GetCharacter(i).
        END.
        cList = cList + CHR(1).
    END.
    IF reqInt64("olderThanSec") <> ? THEN tOld = ADD-INTERVAL(NOW, - INTEGER(reqInt64("olderThanSec")), "seconds").
    FOR EACH LoaderUnit NO-LOCK WHERE LoaderUnit.LoaderRunId = reqInt64("run") AND LoaderUnit.UnitStatus = "C":
        IF NOT ((cList <> "" AND INDEX(cList, CHR(1) + LoaderUnit.ClaimedBy + CHR(1)) > 0)
                OR (tOld <> ? AND LoaderUnit.HeartbeatAt < tOld)) THEN NEXT.
        DO TRANSACTION:
            FIND bUnit WHERE ROWID(bUnit) = ROWID(LoaderUnit) EXCLUSIVE-LOCK.
            IF bUnit.UnitStatus = "C" THEN DO:
                ASSIGN bUnit.UnitStatus = "P" bUnit.ClaimedBy = "".
                n = n + 1.
            END.
        END.
        RELEASE bUnit.
    END.
    oResp:Add("released", n).
END PROCEDURE.

/* Unit counts by status, claims, recent completions, and BenchmarkTableInfo (data file). */
PROCEDURE opStatus:
    DEFINE VARIABLE iRun    AS INT64       NO-UNDO.
    DEFINE VARIABLE nP      AS INTEGER     NO-UNDO.
    DEFINE VARIABLE nC      AS INTEGER     NO-UNDO.
    DEFINE VARIABLE nD      AS INTEGER     NO-UNDO.
    DEFINE VARIABLE nRecent AS INTEGER     NO-UNDO.
    DEFINE VARIABLE iRecentRows AS INT64   NO-UNDO.
    DEFINE VARIABLE iDoneRows AS INT64     NO-UNDO.
    DEFINE VARIABLE tRecent AS DATETIME-TZ NO-UNDO.
    DEFINE VARIABLE oClaims AS JsonArray   NO-UNDO.
    DEFINE VARIABLE oC      AS JsonObject  NO-UNDO.
    DEFINE VARIABLE cFile   AS CHARACTER   NO-UNDO.
    DEFINE VARIABLE n       AS INT64       NO-UNDO.
    tRecent = ADD-INTERVAL(NOW, -300, "seconds").
    oClaims = NEW JsonArray().
    FIND LAST LoaderRun NO-LOCK USE-INDEX PkLoaderRun NO-ERROR.
    IF AVAILABLE LoaderRun THEN DO:
        iRun = LoaderRun.LoaderRunId.
        FOR EACH LoaderUnit NO-LOCK WHERE LoaderUnit.LoaderRunId = iRun:
            CASE LoaderUnit.UnitStatus:
                WHEN "P" THEN nP = nP + 1.
                WHEN "C" THEN DO:
                    nC = nC + 1.
                    oC = NEW JsonObject().
                    oC:Add("unitNo", LoaderUnit.UnitNo).
                    oC:Add("claimedBy", LoaderUnit.ClaimedBy).
                    oC:Add("heartbeatAt", LoaderUnit.HeartbeatAt).
                    oClaims:Add(oC).
                END.
                WHEN "D" THEN DO:
                    ASSIGN nD = nD + 1 iDoneRows = iDoneRows + LoaderUnit.TotalRows.
                    IF LoaderUnit.DoneAt >= tRecent THEN
                        ASSIGN nRecent = nRecent + 1 iRecentRows = iRecentRows + LoaderUnit.TotalRows.
                END.
            END CASE.
        END.
        oResp:Add("run", iRun).
    END.
    ELSE oResp:AddNull("run").
    oResp:Add("pending", nP).
    oResp:Add("claimed", nC).
    oResp:Add("done", nD).
    oResp:Add("doneRows", iDoneRows).
    oResp:Add("recentUnits", nRecent).
    oResp:Add("recentRows", iRecentRows).
    oResp:Add("claims", oClaims).
    cFile = dataFile().
    RUN dumpRows ("LoaderRun", "BY LoaderRun.LoaderRunId", cFile + ".runs", OUTPUT n).
    RUN dumpRows ("BenchmarkTableInfo", "BY BenchmarkTableInfo.TableName", cFile + ".bti", OUTPUT n).
    oResp:Add("runsFile", cFile + ".runs").
    oResp:Add("btiFile", cFile + ".bti").
END PROCEDURE.

/* Rows of a table where RandomInt1000 = k (optionally limited to <Table>Id <= maxId), to a data file. */
PROCEDURE opSample:
    DEFINE VARIABLE cTable AS CHARACTER NO-UNDO.
    DEFINE VARIABLE cWhere AS CHARACTER NO-UNDO.
    DEFINE VARIABLE cFile  AS CHARACTER NO-UNDO.
    DEFINE VARIABLE n      AS INT64     NO-UNDO.
    cTable = reqChar("table").
    cWhere = "WHERE " + cTable + ".RandomInt1000 = " + STRING(reqInt64("k")).
    IF reqInt64("maxId") <> ? THEN
        cWhere = cWhere + " AND " + cTable + "." + cTable + "Id <= " + STRING(reqInt64("maxId")).
    cWhere = cWhere + " BY " + cTable + "." + cTable + "Id".
    cFile = dataFile().
    RUN dumpRows (cTable, cWhere, cFile, OUTPUT n).
    oResp:Add("file", cFile).
    oResp:Add("rows", n).
END PROCEDURE.

/* ====================================================================== main loop */

cSpool = SESSION:PARAMETER.
IF cSpool = "" OR cSpool = ? THEN DO:
    PUT UNFORMATTED "pbgen_agent.p: -param must be the spool directory" SKIP.
    QUIT.
END.
RUN buildUnitDataset.
oParser = NEW ObjectModelParser().
iIdleMs = ETIME.

mainLoop:
REPEAT:
    cReqFile = cSpool + "/req-" + STRING(iSeq) + ".json".
    FILE-INFO:FILE-NAME = cReqFile.
    IF FILE-INFO:FULL-PATHNAME = ? THEN DO:
        IF ETIME - iIdleMs > {&IDLE_LIMIT_MS} THEN LEAVE mainLoop.
        PAUSE 0.05 NO-MESSAGE.
        NEXT mainLoop.
    END.
    oResp = NEW JsonObject().
    DO ON ERROR UNDO, LEAVE:
        oReq = CAST(oParser:ParseFile(cReqFile), JsonObject).
        CASE reqChar("op"):
            WHEN "hello"     THEN RUN opHello.
            WHEN "plan"      THEN RUN opPlan.
            WHEN "state"     THEN RUN opState.
            WHEN "claim"     THEN RUN opClaim.
            WHEN "heartbeat" THEN RUN opHeartbeat.
            WHEN "load"      THEN RUN opLoad.
            WHEN "watermark" THEN RUN opWatermark.
            WHEN "finalize"  THEN RUN opFinalize.
            WHEN "release"   THEN RUN opRelease.
            WHEN "status"    THEN RUN opStatus.
            WHEN "sample"    THEN RUN opSample.
            WHEN "quit"      THEN lQuit = TRUE.
            OTHERWISE UNDO, THROW NEW Progress.Lang.AppError("unknown op " + QUOTER(reqChar("op")), 1).
        END CASE.
        oResp:Add("ok", TRUE).
        CATCH eErr AS Progress.Lang.Error:
            oResp = NEW JsonObject().
            oResp:Add("ok", FALSE).
            oResp:Add("error", eErr:GetMessage(1)).
        END CATCH.
    END.
    oResp:WriteFile(cSpool + "/resp-" + STRING(iSeq) + ".json.tmp", FALSE).
    OS-RENAME VALUE(cSpool + "/resp-" + STRING(iSeq) + ".json.tmp") VALUE(cSpool + "/resp-" + STRING(iSeq) + ".json").
    OS-DELETE VALUE(cReqFile).
    iSeq = iSeq + 1.
    iIdleMs = ETIME.
    IF lQuit THEN LEAVE mainLoop.
END.
QUIT.
