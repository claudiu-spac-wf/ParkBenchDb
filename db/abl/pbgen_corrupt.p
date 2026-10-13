/*------------------------------------------------------------------------
    File        : db/abl/pbgen_corrupt.p
    Purpose     : TEST ONLY. Injects and undoes one data corruption so tests/test_pbgen_integration.py
                  can show that `pbgen check` catches it (spec 003 T046, SC-005).
    Usage       : _progres -b -db <db> -p db/abl/pbgen_corrupt.p -param "<apply|restore>|<case>|<save-file>"
    Cases       : gap        delete Customer 5
                  fk         Account (first with RandomInt1000 = 1): BranchId = 999999
                  randomint  DebitTransaction 1: RandomInt100 = 0
                  stmttotal  AccountStatement (first with RandomInt1000 = 1): TotalDebits + 1
                  bti        BenchmarkTableInfo "Card": MaxId - 1
                  duplicate  a copy of Payee 1 under the ID MaxId + 1
                  claim      LoaderUnit 1: UnitStatus = "C" (looks like a running pbgen worker)
    Notes       : apply saves the original row to <save-file> (temp-table JSON); restore writes it
                  back (or, for duplicate, deletes the added row). Prints "CORRUPT OK" on success.
  ----------------------------------------------------------------------*/

DEFINE VARIABLE cMode  AS CHARACTER NO-UNDO.
DEFINE VARIABLE cCase  AS CHARACTER NO-UNDO.
DEFINE VARIABLE cSave  AS CHARACTER NO-UNDO.
DEFINE VARIABLE cTable AS CHARACTER NO-UNDO.
DEFINE VARIABLE cWhere AS CHARACTER NO-UNDO.
DEFINE VARIABLE hBuf   AS HANDLE    NO-UNDO.
DEFINE VARIABLE hTT    AS HANDLE    NO-UNDO.
DEFINE VARIABLE hTTBuf AS HANDLE    NO-UNDO.
DEFINE VARIABLE iMax   AS INT64     NO-UNDO.
DEFINE VARIABLE iId    AS INT64     NO-UNDO.

ASSIGN
    cMode = ENTRY(1, SESSION:PARAMETER, "|")
    cCase = ENTRY(2, SESSION:PARAMETER, "|")
    cSave = ENTRY(3, SESSION:PARAMETER, "|").

CASE cCase:
    WHEN "gap"       THEN ASSIGN cTable = "Customer"           cWhere = "WHERE Customer.CustomerId = 5".
    WHEN "fk"        THEN ASSIGN cTable = "Account"            cWhere = "WHERE Account.RandomInt1000 = 1".
    WHEN "randomint" THEN ASSIGN cTable = "DebitTransaction"   cWhere = "WHERE DebitTransaction.DebitTransactionId = 1".
    WHEN "stmttotal" THEN ASSIGN cTable = "AccountStatement"   cWhere = "WHERE AccountStatement.RandomInt1000 = 1".
    WHEN "bti"       THEN ASSIGN cTable = "BenchmarkTableInfo" cWhere = "WHERE BenchmarkTableInfo.TableName = 'Card'".
    WHEN "duplicate" THEN ASSIGN cTable = "Payee"              cWhere = "WHERE Payee.PayeeId = 1".
    WHEN "claim"     THEN ASSIGN cTable = "LoaderUnit"         cWhere = "WHERE LoaderUnit.UnitNo = 1".
    OTHERWISE DO:
        PUT UNFORMATTED "CORRUPT FAILED: unknown case " cCase SKIP.
        QUIT.
    END.
END CASE.

CREATE BUFFER hBuf FOR TABLE cTable.
CREATE TEMP-TABLE hTT.
hTT:ADD-FIELDS-FROM(cTable).
hTT:TEMP-TABLE-PREPARE(cTable).
hTTBuf = hTT:DEFAULT-BUFFER-HANDLE.

DO TRANSACTION:
    IF cMode = "apply" THEN DO:
        hBuf:FIND-FIRST(cWhere, EXCLUSIVE-LOCK).
        hTTBuf:BUFFER-CREATE().
        hTTBuf:BUFFER-COPY(hBuf).
        CASE cCase:
            WHEN "gap"       THEN hBuf:BUFFER-DELETE().
            WHEN "claim"     THEN hBuf:BUFFER-FIELD("UnitStatus"):BUFFER-VALUE = "C".
            WHEN "fk"        THEN hBuf:BUFFER-FIELD("BranchId"):BUFFER-VALUE = 999999.
            WHEN "randomint" THEN hBuf:BUFFER-FIELD("RandomInt100"):BUFFER-VALUE = 0.
            WHEN "stmttotal" THEN hBuf:BUFFER-FIELD("TotalDebits"):BUFFER-VALUE =
                                  hBuf:BUFFER-FIELD("TotalDebits"):BUFFER-VALUE + 1.
            WHEN "bti"       THEN hBuf:BUFFER-FIELD("MaxId"):BUFFER-VALUE =
                                  hBuf:BUFFER-FIELD("MaxId"):BUFFER-VALUE - 1.
            WHEN "duplicate" THEN DO:
                hBuf:FIND-LAST("", NO-LOCK).     /* primary index PkPayee: the highest PayeeId */
                iMax = hBuf:BUFFER-FIELD("PayeeId"):BUFFER-VALUE.
                hBuf:BUFFER-CREATE().
                hBuf:BUFFER-COPY(hTTBuf, "PayeeId").
                hBuf:BUFFER-FIELD("PayeeId"):BUFFER-VALUE = iMax + 1.
                hTTBuf:BUFFER-FIELD("PayeeId"):BUFFER-VALUE = iMax + 1.
            END.
        END CASE.
        hBuf:BUFFER-RELEASE().
        hTT:WRITE-JSON("file", cSave, FALSE, "UTF-8").
    END.
    ELSE DO:
        hTT:READ-JSON("file", cSave, "empty").
        hTTBuf:FIND-FIRST().
        IF cCase = "claim" THEN
            hBuf:FIND-FIRST(cWhere, EXCLUSIVE-LOCK) NO-ERROR.
        ELSE DO:
            iId = hTTBuf:BUFFER-FIELD(cTable + "Id"):BUFFER-VALUE.
            hBuf:FIND-FIRST(SUBSTITUTE("WHERE &1.&1Id = &2", cTable, iId), EXCLUSIVE-LOCK) NO-ERROR.
        END.
        IF cCase = "duplicate" THEN hBuf:BUFFER-DELETE().
        ELSE DO:
            IF NOT hBuf:AVAILABLE THEN hBuf:BUFFER-CREATE().
            hBuf:BUFFER-COPY(hTTBuf).
        END.
        hBuf:BUFFER-RELEASE().
    END.
END.

PUT UNFORMATTED "CORRUPT OK " cMode " " cCase SKIP.
QUIT.
