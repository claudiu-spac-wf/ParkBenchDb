/*------------------------------------------------------------------------
    File        : db/abl/pbgen_check.p
    Purpose     : In-database data check for pbgen (feature 003, US5, research R10).
    Usage       : _progres -b <connection> -rereadnolock -cpinternal UTF-8 -cpstream UTF-8
                      -p db/abl/pbgen_check.p -param "<in.json>|<out.json>"
    Input       : {"mode": "sample"|"full", "sampleThreshold": 1000000,
                   "tables": [{"name": T, "fks": [{"field": f, "parent": P, "parentField": pf, "optional": b}]}]}
                  (written by pbgen/check.py from the schema)
    Output      : JSON array of {check, table, ok, detail, sampleSize, exampleId}.
    Notes       : Density is counted exactly for tables below sampleThreshold rows (all tables in
                  full mode); larger tables are checked through BenchmarkTableInfo, first/last ID and
                  1,000 ID probes. FKs and derived rules use the RandomInt1000 = 1 sample on large tables.
  ----------------------------------------------------------------------*/

USING Progress.Json.ObjectModel.*.

DEFINE VARIABLE oIn      AS JsonObject NO-UNDO.
DEFINE VARIABLE oOut     AS JsonArray  NO-UNDO.
DEFINE VARIABLE oTables  AS JsonArray  NO-UNDO.
DEFINE VARIABLE oTable   AS JsonObject NO-UNDO.
DEFINE VARIABLE cMode    AS CHARACTER  NO-UNDO.
DEFINE VARIABLE iThresh  AS INT64      NO-UNDO.
DEFINE VARIABLE i        AS INTEGER    NO-UNDO.

PROCEDURE addResult:
    DEFINE INPUT PARAMETER pcCheck  AS CHARACTER NO-UNDO.
    DEFINE INPUT PARAMETER pcTable  AS CHARACTER NO-UNDO.
    DEFINE INPUT PARAMETER plOk     AS LOGICAL   NO-UNDO.
    DEFINE INPUT PARAMETER pcDetail AS CHARACTER NO-UNDO.
    DEFINE INPUT PARAMETER piSample AS INT64     NO-UNDO.
    DEFINE INPUT PARAMETER piId     AS INT64     NO-UNDO.
    DEFINE VARIABLE o AS JsonObject NO-UNDO.
    o = NEW JsonObject().
    o:Add("check", pcCheck).
    o:Add("table", pcTable).
    o:Add("ok", plOk).
    o:Add("detail", pcDetail).
    o:Add("sampleSize", piSample).
    o:Add("exampleId", piId).
    oOut:Add(o).
END PROCEDURE.

/* first or last <T>Id through the primary (Pk) index */
FUNCTION edgeId RETURNS INT64 (INPUT pcTable AS CHARACTER, INPUT plLast AS LOGICAL):
    DEFINE VARIABLE hB AS HANDLE NO-UNDO.
    DEFINE VARIABLE v  AS INT64  NO-UNDO INITIAL 0.
    CREATE BUFFER hB FOR TABLE pcTable.
    IF plLast THEN hB:FIND-LAST("", NO-LOCK) NO-ERROR.
    ELSE hB:FIND-FIRST("", NO-LOCK) NO-ERROR.
    IF hB:AVAILABLE THEN v = hB:BUFFER-FIELD(pcTable + "Id"):BUFFER-VALUE.
    DELETE OBJECT hB.
    RETURN v.
END FUNCTION.

FUNCTION countRows RETURNS INT64 (INPUT pcTable AS CHARACTER):
    DEFINE VARIABLE hB AS HANDLE NO-UNDO.
    DEFINE VARIABLE hQ AS HANDLE NO-UNDO.
    DEFINE VARIABLE n  AS INT64  NO-UNDO.
    CREATE BUFFER hB FOR TABLE pcTable.
    CREATE QUERY hQ.
    hQ:SET-BUFFERS(hB).
    hQ:QUERY-PREPARE("FOR EACH " + pcTable + " FIELDS(" + pcTable + "Id) NO-LOCK").
    hQ:QUERY-OPEN().
    hQ:GET-FIRST().
    DO WHILE NOT hQ:QUERY-OFF-END:
        n = n + 1.
        hQ:GET-NEXT().
    END.
    DELETE OBJECT hQ.
    DELETE OBJECT hB.
    RETURN n.
END FUNCTION.

FUNCTION findWhere RETURNS LOGICAL (INPUT pcTable AS CHARACTER, INPUT pcWhere AS CHARACTER):
    DEFINE VARIABLE hB AS HANDLE  NO-UNDO.
    DEFINE VARIABLE l  AS LOGICAL NO-UNDO.
    CREATE BUFFER hB FOR TABLE pcTable.
    hB:FIND-FIRST(pcWhere, NO-LOCK) NO-ERROR.
    l = hB:AVAILABLE.
    DELETE OBJECT hB.
    RETURN l.
END FUNCTION.

/* ---------------------------------------------------------------- per-table generic checks */
PROCEDURE checkTable:
    DEFINE INPUT PARAMETER poTable AS JsonObject NO-UNDO.
    DEFINE VARIABLE cT      AS CHARACTER NO-UNDO.
    DEFINE VARIABLE iMin    AS INT64     NO-UNDO.
    DEFINE VARIABLE iMax    AS INT64     NO-UNDO.
    DEFINE VARIABLE iCount  AS INT64     NO-UNDO INITIAL ?.
    DEFINE VARIABLE iBtiMax AS INT64     NO-UNDO.
    DEFINE VARIABLE iBtiCnt AS INT64     NO-UNDO.
    DEFINE VARIABLE lSample AS LOGICAL   NO-UNDO.
    DEFINE VARIABLE oFks    AS JsonArray NO-UNDO.
    DEFINE VARIABLE oFk     AS JsonObject NO-UNDO.
    DEFINE VARIABLE j       AS INTEGER   NO-UNDO.
    DEFINE VARIABLE n       AS INTEGER   NO-UNDO.
    DEFINE VARIABLE iMissing AS INT64    NO-UNDO.
    DEFINE VARIABLE iProbe  AS INT64     NO-UNDO.
    DEFINE VARIABLE hB      AS HANDLE    NO-UNDO.
    DEFINE VARIABLE hQ      AS HANDLE    NO-UNDO.
    DEFINE VARIABLE hP      AS HANDLE    NO-UNDO.
    DEFINE VARIABLE vVal    AS CHARACTER NO-UNDO.
    DEFINE VARIABLE iSample AS INT64     NO-UNDO.
    DEFINE VARIABLE iBad    AS INT64     NO-UNDO.
    DEFINE VARIABLE iBadId  AS INT64     NO-UNDO.
    DEFINE VARIABLE cWhere  AS CHARACTER NO-UNDO.
    DEFINE BUFFER bBti FOR BenchmarkTableInfo.

    cT = poTable:GetCharacter("name").
    FIND bBti NO-LOCK WHERE bBti.TableName = cT NO-ERROR.
    ASSIGN
        iBtiMax = IF AVAILABLE bBti THEN bBti.MaxId ELSE -1
        iBtiCnt = IF AVAILABLE bBti THEN bBti.TableRowCount ELSE -1
        iMin    = edgeId(cT, FALSE)
        iMax    = edgeId(cT, TRUE)
        lSample = cMode <> "full" AND iBtiCnt >= iThresh.

    /* density and BenchmarkTableInfo */
    IF NOT lSample THEN DO:
        iCount = countRows(cT).
        RUN addResult ("density", cT, iCount = iMax AND (iMin = 1 OR iCount = 0),
            SUBSTITUTE("rows &1, first id &2, last id &3", iCount, iMin, iMax), iCount,
            IF iCount = iMax THEN 0 ELSE iMax).
    END.
    ELSE DO:
        DO j = 1 TO 1000:
            iProbe = RANDOM(1, INTEGER(MIN(iMax, 2000000000))).
            IF NOT findWhere(cT, "WHERE " + cT + "." + cT + "Id = " + STRING(iProbe)) THEN DO:
                iMissing = iMissing + 1.
                IF iBadId = 0 THEN iBadId = iProbe.
            END.
        END.
        RUN addResult ("density", cT, iMissing = 0 AND iMin = 1,
            SUBSTITUTE("sampled: first id &1, last id &2, &3 of 1000 probed ids missing", iMin, iMax, iMissing),
            1000, iBadId).
        iBadId = 0.
    END.
    RUN addResult ("BenchmarkTableInfo", cT,
        iBtiMax = iMax AND (iCount = ? OR iBtiCnt = iCount) AND iBtiCnt = iBtiMax,
        SUBSTITUTE("MaxId &1 / TableRowCount &2 vs last id &3&4", iBtiMax, iBtiCnt, iMax,
                   IF iCount = ? THEN "" ELSE ", rows " + STRING(iCount)), 0, 0).

    /* RandomInt ranges: two index range probes per field (an OR would scan the table) */
    DO j = 1 TO 3:
        n = INTEGER(ENTRY(j, "10,100,1000")).
        IF findWhere(cT, SUBSTITUTE("WHERE &1.RandomInt&2 < 1", cT, n))
           OR findWhere(cT, SUBSTITUTE("WHERE &1.RandomInt&2 > &2", cT, n)) THEN
            RUN addResult ("RandomInt" + STRING(n), cT, FALSE, "value outside 1-" + STRING(n), 0, 0).
        ELSE RUN addResult ("RandomInt" + STRING(n), cT, TRUE, "all within 1-" + STRING(n), 0, 0).
    END.

    /* foreign keys: all rows of small tables, RandomInt1000 = 1 on large ones */
    oFks = poTable:GetJsonArray("fks").
    IF oFks:Length = 0 THEN RETURN.
    cWhere = IF lSample THEN SUBSTITUTE("WHERE &1.RandomInt1000 = 1", cT) ELSE "".
    DO j = 1 TO oFks:Length:
        oFk = oFks:GetJsonObject(j).
        ASSIGN iSample = 0 iBad = 0 iBadId = 0.
        CREATE BUFFER hB FOR TABLE cT.
        CREATE BUFFER hP FOR TABLE oFk:GetCharacter("parent").
        CREATE QUERY hQ.
        hQ:SET-BUFFERS(hB).
        hQ:QUERY-PREPARE(SUBSTITUTE("FOR EACH &1 NO-LOCK &2", cT, cWhere)).
        hQ:QUERY-OPEN().
        hQ:GET-FIRST().
        DO WHILE NOT hQ:QUERY-OFF-END:
            iSample = iSample + 1.
            vVal = STRING(hB:BUFFER-FIELD(oFk:GetCharacter("field")):BUFFER-VALUE).
            IF NOT (oFk:GetLogical("optional") AND vVal = "0") THEN DO:
                hP:FIND-FIRST(SUBSTITUTE("WHERE &1.&2 = &3", oFk:GetCharacter("parent"),
                    oFk:GetCharacter("parentField"), QUOTER(vVal)), NO-LOCK) NO-ERROR.
                IF NOT hP:AVAILABLE THEN DO:
                    iBad = iBad + 1.
                    IF iBadId = 0 THEN iBadId = hB:BUFFER-FIELD(cT + "Id"):BUFFER-VALUE.
                END.
            END.
            hQ:GET-NEXT().
        END.
        DELETE OBJECT hQ.
        DELETE OBJECT hB.
        DELETE OBJECT hP.
        RUN addResult ("fk." + oFk:GetCharacter("field"), cT, iBad = 0,
            SUBSTITUTE("&1 of &2 rows point at a missing &3", iBad, iSample, oFk:GetCharacter("parent")),
            iSample, iBadId).
    END.
END PROCEDURE.

/* ---------------------------------------------------------------- derived rules (sampled) */
PROCEDURE checkDerived:
    DEFINE VARIABLE dDeb    AS DECIMAL NO-UNDO.
    DEFINE VARIABLE dCred   AS DECIMAL NO-UNDO.
    DEFINE VARIABLE iDeb    AS INTEGER NO-UNDO.
    DEFINE VARIABLE iCred   AS INTEGER NO-UNDO.
    DEFINE VARIABLE iSeen      AS INT64   NO-UNDO.
    DEFINE VARIABLE iBad    AS INT64   NO-UNDO.
    DEFINE VARIABLE iBadId  AS INT64   NO-UNDO.
    DEFINE VARIABLE dLast   AS DECIMAL NO-UNDO.
    DEFINE VARIABLE dPct    AS DECIMAL NO-UNDO.
    DEFINE VARIABLE iPrim   AS INTEGER NO-UNDO.
    DEFINE BUFFER bStmt  FOR AccountStatement.
    DEFINE BUFFER bPrev  FOR AccountStatement.
    DEFINE BUFFER bDeb   FOR DebitTransaction.
    DEFINE BUFFER bCred  FOR CreditTransaction.
    DEFINE BUFFER bAcct  FOR Account.
    DEFINE BUFFER bHold  FOR AccountHolder.
    DEFINE BUFFER bXfer  FOR Transfer.

    /* statement totals and opening/closing chain */
    FOR EACH bStmt NO-LOCK WHERE bStmt.RandomInt1000 = 1:
        ASSIGN dDeb = 0 dCred = 0 iDeb = 0 iCred = 0 iSeen = iSeen + 1.
        FOR EACH bDeb NO-LOCK WHERE bDeb.AccountStatementId = bStmt.AccountStatementId:
            ASSIGN dDeb = dDeb + bDeb.Amount iDeb = iDeb + 1.
        END.
        FOR EACH bCred NO-LOCK WHERE bCred.AccountStatementId = bStmt.AccountStatementId:
            ASSIGN dCred = dCred + bCred.Amount iCred = iCred + 1.
        END.
        FIND FIRST bPrev NO-LOCK WHERE bPrev.AccountId = bStmt.AccountId AND bPrev.PeriodEnd < bStmt.PeriodEnd
            USE-INDEX UxAccountPeriod NO-ERROR.
        IF dDeb <> bStmt.TotalDebits OR dCred <> bStmt.TotalCredits OR iDeb <> bStmt.DebitCount
           OR iCred <> bStmt.CreditCount
           OR bStmt.ClosingBalance <> bStmt.OpeningBalance - bStmt.TotalDebits + bStmt.TotalCredits
           OR (AVAILABLE bPrev AND bPrev.ClosingBalance <> bStmt.OpeningBalance) THEN DO:
            iBad = iBad + 1.
            IF iBadId = 0 THEN iBadId = bStmt.AccountStatementId.
        END.
    END.
    RUN addResult ("derived.statementTotals", "AccountStatement", iBad = 0,
        SUBSTITUTE("&1 of &2 sampled statements disagree with their transactions or the previous closing", iBad, iSeen),
        iSeen, iBadId).

    /* current balance = running balance of the newest transaction */
    ASSIGN iSeen = 0 iBad = 0 iBadId = 0.
    FOR EACH bAcct NO-LOCK WHERE bAcct.RandomInt1000 = 1:
        FIND FIRST bDeb NO-LOCK WHERE bDeb.AccountId = bAcct.AccountId USE-INDEX IxAccountPosted NO-ERROR.
        FIND FIRST bCred NO-LOCK WHERE bCred.AccountId = bAcct.AccountId USE-INDEX IxAccountPosted NO-ERROR.
        IF NOT AVAILABLE bDeb AND NOT AVAILABLE bCred THEN NEXT.
        iSeen = iSeen + 1.
        IF AVAILABLE bDeb AND (NOT AVAILABLE bCred OR bDeb.PostedAt > bCred.PostedAt) THEN dLast = bDeb.RunningBalance.
        ELSE IF AVAILABLE bCred AND (NOT AVAILABLE bDeb OR bCred.PostedAt > bDeb.PostedAt) THEN dLast = bCred.RunningBalance.
        ELSE dLast = ?.  /* same timestamp: accept either */
        IF (dLast <> ? AND dLast <> bAcct.CurrentBalance)
           OR (dLast = ? AND bAcct.CurrentBalance <> bDeb.RunningBalance AND bAcct.CurrentBalance <> bCred.RunningBalance) THEN DO:
            iBad = iBad + 1.
            IF iBadId = 0 THEN iBadId = bAcct.AccountId.
        END.
    END.
    RUN addResult ("derived.currentBalance", "Account", iBad = 0,
        SUBSTITUTE("&1 of &2 sampled accounts differ from their newest running balance", iBad, iSeen), iSeen, iBadId).

    /* holders: ownership 100%, exactly one PRIMARY */
    ASSIGN iSeen = 0 iBad = 0 iBadId = 0.
    FOR EACH bAcct NO-LOCK WHERE bAcct.RandomInt1000 = 1:
        ASSIGN iSeen = iSeen + 1 dPct = 0 iPrim = 0.
        FOR EACH bHold NO-LOCK WHERE bHold.AccountId = bAcct.AccountId:
            dPct = dPct + bHold.OwnershipPercent.
            IF bHold.HolderRole = "PRIMARY" THEN iPrim = iPrim + 1.
        END.
        IF dPct <> 100 OR iPrim <> 1 THEN DO:
            iBad = iBad + 1.
            IF iBadId = 0 THEN iBadId = bAcct.AccountId.
        END.
    END.
    RUN addResult ("derived.accountHolders", "AccountHolder", iBad = 0,
        SUBSTITUTE("&1 of &2 sampled accounts do not have 100% ownership and one PRIMARY", iBad, iSeen), iSeen, iBadId).

    /* transfers own one debit and one credit of the same amount */
    ASSIGN iSeen = 0 iBad = 0 iBadId = 0.
    FOR EACH bXfer NO-LOCK WHERE bXfer.RandomInt1000 = 1:
        iSeen = iSeen + 1.
        FIND bDeb NO-LOCK WHERE bDeb.DebitTransactionId = bXfer.DebitTransactionId NO-ERROR.
        FIND bCred NO-LOCK WHERE bCred.CreditTransactionId = bXfer.CreditTransactionId NO-ERROR.
        IF NOT AVAILABLE bDeb OR NOT AVAILABLE bCred OR bDeb.Amount <> bXfer.Amount OR bCred.Amount <> bXfer.Amount
           OR bDeb.AccountId <> bXfer.FromAccountId OR bCred.AccountId <> bXfer.ToAccountId THEN DO:
            iBad = iBad + 1.
            IF iBadId = 0 THEN iBadId = bXfer.TransferId.
        END.
    END.
    RUN addResult ("derived.transfers", "Transfer", iBad = 0,
        SUBSTITUTE("&1 of &2 sampled transfers do not match their debit and credit", iBad, iSeen), iSeen, iBadId).
END PROCEDURE.

/* ---------------------------------------------------------------- main */
oIn = CAST(NEW ObjectModelParser():ParseFile(ENTRY(1, SESSION:PARAMETER, "|")), JsonObject).
oOut = NEW JsonArray().
cMode = oIn:GetCharacter("mode").
iThresh = oIn:GetInt64("sampleThreshold").
oTables = oIn:GetJsonArray("tables").
DO i = 1 TO oTables:Length:
    RUN checkTable (oTables:GetJsonObject(i)).
END.
RUN checkDerived.
oOut:WriteFile(ENTRY(2, SESSION:PARAMETER, "|"), FALSE).
QUIT.
