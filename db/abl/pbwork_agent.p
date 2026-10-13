/* Persistent, read-only ParkBench workload agent. One process per Python worker.
   The protocol is req-N.json / resp-N.json, shared with pbgen_agent.p. */
USING Progress.Json.ObjectModel.*.

DEFINE VARIABLE cSpool AS CHARACTER NO-UNDO.
DEFINE VARIABLE iSeq AS INTEGER NO-UNDO INITIAL 1.
DEFINE VARIABLE cRequest AS CHARACTER NO-UNDO.
DEFINE VARIABLE iIdleMs AS INT64 NO-UNDO.
DEFINE VARIABLE oParser AS ObjectModelParser NO-UNDO.
DEFINE VARIABLE oReq AS JsonObject NO-UNDO.
DEFINE VARIABLE oResp AS JsonObject NO-UNDO.
DEFINE VARIABLE lQuit AS LOGICAL NO-UNDO.

FUNCTION allowedTable RETURNS LOGICAL (INPUT pcTable AS CHARACTER):
    /* These are the only tables reachable from this agent. Never interpolate
       an unvalidated request string into a dynamic query. */
    RETURN LOOKUP(pcTable,
        "Currency,Country,ExchangeRate,Branch,Employee,AccountType,InterestRateHistory,TransactionType,MerchantCategory,Merchant,Customer,CustomerAddress,CustomerContact,CustomerDocument,CustomerNote,Account,AccountHolder,Payee,ScheduledPayment,Card,Loan,StatementDocument,AccountStatement,MonthlyBalance,CreditTransaction,Transfer,LoanPayment,LoginEvent,DebitTransaction,CardAuthorization,AuditLog,BenchmarkTableInfo") > 0.
END FUNCTION.

PROCEDURE opHello:
    oResp:Add("agent_version", "0.1.0").
    oResp:Add("openedge_version", PROVERSION).
    oResp:Add("database", LDBNAME(1)).
    oResp:Add("tables", 32).
    oResp:Add("schema_present", CAN-FIND(FIRST BenchmarkTableInfo)).
END PROCEDURE.

PROCEDURE opValidate:
    DEFINE VARIABLE oPrerequisites AS JsonObject NO-UNDO.
    DEFINE VARIABLE aTables AS JsonArray NO-UNDO.
    DEFINE VARIABLE oTable AS JsonObject NO-UNDO.
    DEFINE VARIABLE oCounts AS JsonObject NO-UNDO.
    DEFINE VARIABLE cTable AS CHARACTER NO-UNDO.
    DEFINE VARIABLE nRows AS INT64 NO-UNDO.
    DEFINE VARIABLE nMin AS INT64 NO-UNDO.
    DEFINE VARIABLE i AS INTEGER NO-UNDO.
    IF NOT oReq:Has("prerequisites") THEN
        UNDO, THROW NEW Progress.Lang.AppError("missing prerequisites", 1).
    oPrerequisites = oReq:GetJsonObject("prerequisites").
    aTables = oPrerequisites:GetJsonArray("tables").
    oCounts = NEW JsonObject().
    DO i = 1 TO aTables:Length:
        oTable = aTables:GetJsonObject(i).
        cTable = oTable:GetCharacter("name").
        nMin = oTable:GetInt64("minimumRows").
        IF NOT allowedTable(cTable) OR nMin < 0 THEN
            UNDO, THROW NEW Progress.Lang.AppError("invalid table prerequisite", 1).
        IF NOT CAN-FIND(FIRST _File WHERE _File._File-Name = cTable) THEN
            UNDO, THROW NEW Progress.Lang.AppError("required schema table is absent: " + cTable, 1).
        IF cTable = "BenchmarkTableInfo" THEN DO:
            nRows = 0.
            FOR EACH BenchmarkTableInfo NO-LOCK: nRows = nRows + 1. END.
        END.
        ELSE DO:
            FIND BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.TableName = cTable NO-ERROR.
            nRows = IF AVAILABLE BenchmarkTableInfo THEN BenchmarkTableInfo.TableRowCount ELSE 0.
        END.
        IF nRows < nMin THEN
            UNDO, THROW NEW Progress.Lang.AppError("minimumRows not met for " + cTable, 1).
        oCounts:Add(cTable, nRows).
    END.
    oResp:Add("available", TRUE).
    oResp:Add("counts", oCounts).
END PROCEDURE.

FUNCTION boundedQuery RETURNS INT64 (INPUT pcTable AS CHARACTER,
                                     INPUT pcWhere AS CHARACTER,
                                     INPUT piLimit AS INTEGER):
    DEFINE VARIABLE hBuffer AS HANDLE NO-UNDO.
    DEFINE VARIABLE hQuery AS HANDLE NO-UNDO.
    DEFINE VARIABLE n AS INT64 NO-UNDO.
    IF NOT allowedTable(pcTable) OR piLimit < 1 OR piLimit > 10000 THEN
        UNDO, THROW NEW Progress.Lang.AppError("invalid bounded read", 1).
    CREATE BUFFER hBuffer FOR TABLE pcTable.
    CREATE QUERY hQuery.
    hQuery:SET-BUFFERS(hBuffer).
    hQuery:QUERY-PREPARE("FOR EACH " + pcTable + " NO-LOCK " + pcWhere).
    hQuery:QUERY-OPEN().
    hQuery:GET-FIRST().
    DO WHILE NOT hQuery:QUERY-OFF-END AND n < piLimit:
        n = n + 1.
        hQuery:GET-NEXT().
    END.
    hQuery:QUERY-CLOSE().
    DELETE OBJECT hQuery.
    DELETE OBJECT hBuffer.
    RETURN n.
END FUNCTION.

PROCEDURE readLob:
    DEFINE INPUT PARAMETER pcTable AS CHARACTER NO-UNDO.
    DEFINE INPUT PARAMETER piKey AS INT64 NO-UNDO.
    DEFINE INPUT PARAMETER pcMode AS CHARACTER NO-UNDO.
    DEFINE OUTPUT PARAMETER piRows AS INT64 NO-UNDO.
    DEFINE VARIABLE lcText AS LONGCHAR NO-UNDO.
    DEFINE VARIABLE mBlob AS MEMPTR NO-UNDO.
    IF LOOKUP(pcMode, "scalarOnly,clob,blob,both") = 0 THEN
        UNDO, THROW NEW Progress.Lang.AppError("invalid LOB mode", 1).
    CASE pcTable:
        WHEN "CustomerDocument" THEN DO:
            IF pcMode = "clob" OR pcMode = "both" THEN
                UNDO, THROW NEW Progress.Lang.AppError("CLOB unavailable on CustomerDocument", 1).
            FIND CustomerDocument NO-LOCK WHERE CustomerDocument.CustomerDocumentId = piKey NO-ERROR.
            IF AVAILABLE CustomerDocument THEN DO:
                piRows = 1.
                IF pcMode = "blob" THEN
                    COPY-LOB FROM CustomerDocument.Content TO mBlob.
            END.
        END.
        WHEN "CustomerNote" THEN DO:
            IF pcMode = "blob" OR pcMode = "both" THEN
                UNDO, THROW NEW Progress.Lang.AppError("BLOB unavailable on CustomerNote", 1).
            FIND CustomerNote NO-LOCK WHERE CustomerNote.CustomerNoteId = piKey NO-ERROR.
            IF AVAILABLE CustomerNote THEN DO:
                piRows = 1.
                IF pcMode = "clob" AND CustomerNote.NoteText <> ? THEN
                    COPY-LOB FROM CustomerNote.NoteText TO lcText.
            END.
        END.
        WHEN "StatementDocument" THEN DO:
            FIND StatementDocument NO-LOCK WHERE StatementDocument.StatementDocumentId = piKey NO-ERROR.
            IF AVAILABLE StatementDocument THEN DO:
                piRows = 1.
                IF pcMode = "clob" OR pcMode = "both" THEN
                    COPY-LOB FROM StatementDocument.StatementXml TO lcText.
                IF pcMode = "blob" OR pcMode = "both" THEN
                    COPY-LOB FROM StatementDocument.PdfContent TO mBlob.
            END.
        END.
        WHEN "AccountStatement" THEN DO:
            IF pcMode = "blob" OR pcMode = "both" THEN
                UNDO, THROW NEW Progress.Lang.AppError("BLOB unavailable on AccountStatement", 1).
            FIND AccountStatement NO-LOCK WHERE AccountStatement.AccountStatementId = piKey NO-ERROR.
            IF AVAILABLE AccountStatement THEN DO:
                piRows = 1.
                IF pcMode = "clob" AND AccountStatement.NoticeText <> ? THEN
                    COPY-LOB FROM AccountStatement.NoticeText TO lcText.
            END.
        END.
        OTHERWISE UNDO, THROW NEW Progress.Lang.AppError("unsupported LOB table", 1).
    END CASE.
    SET-SIZE(mBlob) = 0.
END PROCEDURE.

PROCEDURE navigateCustomer:
    DEFINE INPUT PARAMETER piKey AS INT64 NO-UNDO.
    DEFINE INPUT PARAMETER piDepth AS INTEGER NO-UNDO.
    DEFINE INPUT PARAMETER piLimit AS INTEGER NO-UNDO.
    DEFINE OUTPUT PARAMETER piRows AS INT64 NO-UNDO.
    IF piDepth < 2 OR piDepth > 4 OR piLimit < 1 OR piLimit > 1000 THEN
        UNDO, THROW NEW Progress.Lang.AppError("invalid navigation bounds", 1).
    FIND Customer NO-LOCK WHERE Customer.CustomerId = piKey NO-ERROR.
    IF NOT AVAILABLE Customer THEN RETURN.
    piRows = 1.
    FOR EACH AccountHolder NO-LOCK WHERE AccountHolder.CustomerId = piKey:
        piRows = piRows + 1.
        IF piDepth >= 3 THEN DO:
            FIND Account NO-LOCK WHERE Account.AccountId = AccountHolder.AccountId NO-ERROR.
            IF AVAILABLE Account THEN DO:
                piRows = piRows + 1.
                IF piDepth >= 4 THEN DO:
                    FOR EACH DebitTransaction NO-LOCK WHERE DebitTransaction.AccountId = Account.AccountId:
                        piRows = piRows + 1.
                        IF piRows >= piLimit THEN LEAVE.
                    END.
                END.
            END.
        END.
        IF piRows >= piLimit THEN LEAVE.
    END.
END PROCEDURE.

PROCEDURE opBatch:
    DEFINE VARIABLE aOps AS JsonArray NO-UNDO.
    DEFINE VARIABLE aResults AS JsonArray NO-UNDO.
    DEFINE VARIABLE aRetryKeys AS JsonArray NO-UNDO.
    DEFINE VARIABLE oOp AS JsonObject NO-UNDO.
    DEFINE VARIABLE oResult AS JsonObject NO-UNDO.
    DEFINE VARIABLE cTable AS CHARACTER NO-UNDO.
    DEFINE VARIABLE cField AS CHARACTER NO-UNDO.
    DEFINE VARIABLE hBuffer AS HANDLE NO-UNDO.
    DEFINE VARIABLE nKey AS INT64 NO-UNDO.
    DEFINE VARIABLE nStart AS INTEGER NO-UNDO.
    DEFINE VARIABLE nRows AS INT64 NO-UNDO.
    DEFINE VARIABLE nLimit AS INTEGER NO-UNDO.
    DEFINE VARIABLE cHandler AS CHARACTER NO-UNDO.
    DEFINE VARIABLE cWhere AS CHARACTER NO-UNDO.
    DEFINE VARIABLE cIndexed AS CHARACTER NO-UNDO.
    DEFINE VARIABLE i AS INTEGER NO-UNDO.
    DEFINE VARIABLE j AS INTEGER NO-UNDO.
    DEFINE VARIABLE nRetries AS INTEGER NO-UNDO.
    aOps = oReq:GetJsonArray("operations").
    IF aOps:Length < 1 OR aOps:Length > 256 THEN
        UNDO, THROW NEW Progress.Lang.AppError("batch size must be 1..256", 1).
    aResults = NEW JsonArray().
    DO i = 1 TO aOps:Length:
        oOp = aOps:GetJsonObject(i).
        cHandler = oOp:GetCharacter("handler").
        IF LOOKUP(cHandler, "point_lookup,indexed_selective,range_scan,table_scan,relationship_navigation,lob_fetch") = 0 THEN
            UNDO, THROW NEW Progress.Lang.AppError("unavailable workload handler", 1).
        cTable = oOp:GetCharacter("table").
        IF NOT allowedTable(cTable) THEN
            UNDO, THROW NEW Progress.Lang.AppError("unknown workload table", 1).
        nStart = ETIME.
        nRows = 0.
        nRetries = 0.
        CASE cHandler:
            WHEN "point_lookup" THEN DO:
                nKey = oOp:GetInt64("key_id").
                IF nKey < 1 THEN UNDO, THROW NEW Progress.Lang.AppError("invalid primary key", 1).
                cField = cTable + "Id".
                CREATE BUFFER hBuffer FOR TABLE cTable.
                hBuffer:FIND-FIRST("WHERE " + cTable + "." + cField + " = " + STRING(nKey), NO-LOCK) NO-ERROR.
                IF hBuffer:AVAILABLE THEN nRows = 1.
                IF nRows = 0 AND oOp:Has("retry_keys") THEN DO:
                    aRetryKeys = oOp:GetJsonArray("retry_keys").
                    IF aRetryKeys:Length > 3 THEN
                        UNDO, THROW NEW Progress.Lang.AppError("too many point-key retries", 1).
                    DO j = 1 TO aRetryKeys:Length WHILE nRows = 0:
                        nKey = aRetryKeys:GetInt64(j).
                        IF nKey < 1 THEN
                            UNDO, THROW NEW Progress.Lang.AppError("invalid retry primary key", 1).
                        nRetries = nRetries + 1.
                        hBuffer:FIND-FIRST("WHERE " + cTable + "." + cField + " = " + STRING(nKey), NO-LOCK) NO-ERROR.
                        IF hBuffer:AVAILABLE THEN nRows = 1.
                    END.
                END.
                DELETE OBJECT hBuffer.
            END.
            WHEN "indexed_selective" THEN DO:
                cIndexed = oOp:GetCharacter("field").
                IF LOOKUP(cIndexed, "RandomInt10,RandomInt100,RandomInt1000") = 0 THEN
                    UNDO, THROW NEW Progress.Lang.AppError("invalid selective field", 1).
                nKey = oOp:GetInt64("predicate_value").
                nLimit = oOp:GetInteger("limit").
                IF nKey < 1 OR nKey > (IF cIndexed = "RandomInt10" THEN 10 ELSE IF cIndexed = "RandomInt100" THEN 100 ELSE 1000) THEN
                    UNDO, THROW NEW Progress.Lang.AppError("invalid selective value", 1).
                cWhere = "WHERE " + cTable + "." + cIndexed + " = " + STRING(nKey).
                nRows = boundedQuery(cTable, cWhere, nLimit).
            END.
            WHEN "range_scan" THEN DO:
                nKey = oOp:GetInt64("range_start").
                nLimit = oOp:GetInteger("limit").
                IF nKey < 1 THEN UNDO, THROW NEW Progress.Lang.AppError("invalid range start", 1).
                cWhere = "WHERE " + cTable + "." + cTable + "Id >= " + STRING(nKey) + " BY " + cTable + "." + cTable + "Id".
                nRows = boundedQuery(cTable, cWhere, nLimit).
            END.
            WHEN "table_scan" THEN DO:
                nLimit = oOp:GetInteger("limit").
                nRows = boundedQuery(cTable, "", nLimit).
            END.
            WHEN "relationship_navigation" THEN
                RUN navigateCustomer(oOp:GetInt64("key_id"), oOp:GetInteger("depth"), oOp:GetInteger("limit"), OUTPUT nRows).
            WHEN "lob_fetch" THEN
                RUN readLob(cTable, oOp:GetInt64("key_id"), oOp:GetCharacter("lob_mode"), OUTPUT nRows).
        END CASE.
        oResult = NEW JsonObject().
        oResult:Add("ordinal", oOp:GetInt64("ordinal")).
        oResult:Add("operation_id", oOp:GetCharacter("operation_id")).
        oResult:Add("status", "read").
        oResult:Add("rows_read", nRows).
        oResult:Add("rows_written", 0).
        oResult:Add("retry_count", nRetries).
        oResult:Add("retried", nRetries).
        oResult:Add("requested_cardinality", IF oOp:Has("limit") THEN oOp:GetInteger("limit") ELSE 1).
        IF oOp:Has("depth") THEN oResult:Add("traversal_depth", oOp:GetInteger("depth")).
        IF oOp:Has("lob_mode") THEN oResult:Add("lob_mode", oOp:GetCharacter("lob_mode")).
        oResult:Add("elapsed_ms", ETIME - nStart).
        oResult:AddNull("error_class").
        aResults:Add(oResult).
    END.
    oResp:Add("operations", aResults).
END PROCEDURE.

PROCEDURE opSample:
    DEFINE VARIABLE aTables AS JsonArray NO-UNDO.
    DEFINE VARIABLE aRows AS JsonArray NO-UNDO.
    DEFINE VARIABLE aBti AS JsonArray NO-UNDO.
    DEFINE VARIABLE oRow AS JsonObject NO-UNDO.
    DEFINE VARIABLE oSequences AS JsonObject NO-UNDO.
    DEFINE VARIABLE cTable AS CHARACTER NO-UNDO.
    DEFINE VARIABLE i AS INTEGER NO-UNDO.
    aTables = oReq:GetJsonArray("tables").
    aRows = NEW JsonArray().
    aBti = NEW JsonArray().
    oSequences = NEW JsonObject().
    DO i = 1 TO aTables:Length:
        cTable = aTables:GetCharacter(i).
        IF NOT allowedTable(cTable) THEN
            UNDO, THROW NEW Progress.Lang.AppError("unknown workload table", 1).
        FIND BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.TableName = cTable NO-ERROR.
        IF AVAILABLE BenchmarkTableInfo THEN DO:
            oRow = NEW JsonObject().
            oRow:Add("table", cTable).
            oRow:Add("id", BenchmarkTableInfo.MaxId).
            aRows:Add(oRow).
            oRow = NEW JsonObject().
            oRow:Add("table", cTable).
            oRow:Add("row_count", BenchmarkTableInfo.TableRowCount).
            oRow:Add("max_id", BenchmarkTableInfo.MaxId).
            aBti:Add(oRow).
        END.
        oSequences:Add(cTable, DYNAMIC-CURRENT-VALUE("Seq" + cTable + "Id", LDBNAME(1))).
    END.
    oResp:Add("rows", aRows).
    oResp:Add("bti", aBti).
    oResp:Add("sequences", oSequences).
END PROCEDURE.

cSpool = SESSION:PARAMETER.
IF cSpool = ? OR cSpool = "" THEN QUIT.
oParser = NEW ObjectModelParser().
iIdleMs = ETIME.
mainLoop:
REPEAT:
    cRequest = cSpool + "/req-" + STRING(iSeq) + ".json".
    FILE-INFO:FILE-NAME = cRequest.
    IF FILE-INFO:FULL-PATHNAME = ? THEN DO:
        IF ETIME - iIdleMs > 600000 THEN LEAVE mainLoop.
        PAUSE 0.05 NO-MESSAGE.
        NEXT mainLoop.
    END.
    oResp = NEW JsonObject().
    DO ON ERROR UNDO, LEAVE:
        oReq = CAST(oParser:ParseFile(cRequest), JsonObject).
        CASE oReq:GetCharacter("op"):
            WHEN "hello" THEN RUN opHello.
            WHEN "validate" THEN RUN opValidate.
            WHEN "batch" THEN RUN opBatch.
            WHEN "sample" THEN RUN opSample.
            WHEN "quit" THEN lQuit = TRUE.
            OTHERWISE UNDO, THROW NEW Progress.Lang.AppError("unknown workload operation", 1).
        END CASE.
        oResp:Add("ok", TRUE).
        CATCH eErr AS Progress.Lang.Error:
            oResp = NEW JsonObject().
            oResp:Add("ok", FALSE).
            oResp:Add("error", eErr:GetMessage(1)).
        END CATCH.
    END.
    oResp:WriteFile(cSpool + "/resp-" + STRING(iSeq) + ".json.tmp", FALSE).
    OS-RENAME VALUE(cSpool + "/resp-" + STRING(iSeq) + ".json.tmp")
              VALUE(cSpool + "/resp-" + STRING(iSeq) + ".json").
    OS-DELETE VALUE(cRequest).
    iSeq = iSeq + 1.
    iIdleMs = ETIME.
    IF lQuit THEN LEAVE mainLoop.
END.
QUIT.
