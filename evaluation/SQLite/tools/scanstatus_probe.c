/*
 * scanstatus_probe.c — Execute SQL and report real scanned rows via
 * SQLITE_SCANSTAT_NVISIT.
 *
 * Usage:
 *   scanstatus_probe <db_path> <sql>
 *
 * Output (stdout):  JSON with total_scanned_rows.
 * Exit code:        0 on success, 1 on error or timeout.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <unistd.h>
#include "sqlite3.h"

#ifndef SQLITE_ENABLE_STMT_SCANSTATUS
#error "SQLite must be compiled with SQLITE_ENABLE_STMT_SCANSTATUS"
#endif

/* Default SQL execution timeout in seconds.  0 disables. */
#ifndef PROBE_SQL_TIMEOUT_SECONDS
#define PROBE_SQL_TIMEOUT_SECONDS 0
#endif

static volatile int timed_out = 0;

#if PROBE_SQL_TIMEOUT_SECONDS > 0
static void timeout_handler(int sig) {
    (void)sig;
    timed_out = 1;
}
#endif

/*
 * Collect NVISIT from every scan loop on `stmt` *after* sqlite3_step has
 * returned SQLITE_DONE (i.e. the query was fully executed).
 *
 * API: sqlite3_stmt_scanstatus(stmt, idx, iScanStatusOp, pOut)
 *   SQLITE_SCANSTAT_NLOOP with idx=0 returns the total loop count.
 *   SQLITE_SCANSTAT_NVISIT returns rows examined per loop.
 *
 * Returns the sum of all positive NVISIT values, or -1 on error.
 */
static sqlite3_int64 collect_nvisit(sqlite3_stmt *stmt) {
    sqlite3_int64 nloop = 0;
    /* Use the v2 API with SQLITE_SCANSTAT_COMPLEX for maximum coverage
       (aggregates, sub-queries, etc.).  Falls back to plain scanstatus
       on older SQLite builds. */
    int rc = sqlite3_stmt_scanstatus_v2(stmt, 0, SQLITE_SCANSTAT_NLOOP,
                                        SQLITE_SCANSTAT_COMPLEX, &nloop);
    if (rc != 0) {
        /* COMPLEX path failed — try without the flag */
        rc = sqlite3_stmt_scanstatus(stmt, 0, SQLITE_SCANSTAT_NLOOP, &nloop);
    }
    if (rc != 0 || nloop < 0) {
        /* scanstatus entirely unavailable for this statement */
        return -1;
    }
    if (nloop == 0) {
        /* No scan loops (e.g. SELECT 1) — zero rows genuinely scanned. */
        return 0;
    }

    sqlite3_int64 total_nvisit = 0;
    for (sqlite3_int64 i = 0; i < nloop; i++) {
        sqlite3_int64 nvisit = 0;
        rc = sqlite3_stmt_scanstatus_v2(stmt, (int)i, SQLITE_SCANSTAT_NVISIT,
                                        SQLITE_SCANSTAT_COMPLEX, &nvisit);
        if (rc != 0) {
            rc = sqlite3_stmt_scanstatus(stmt, (int)i, SQLITE_SCANSTAT_NVISIT, &nvisit);
        }
        if (rc == 0 && nvisit > 0) {
            total_nvisit += nvisit;
        }
    }
    return total_nvisit;
}

int main(int argc, char **argv) {
    if (argc != 3) {
        fprintf(stderr, "Usage: scanstatus_probe <db_path> <sql>\n");
        return 1;
    }

    const char *db_path = argv[1];
    const char *sql      = argv[2];

    /* Open database */
    sqlite3 *db = NULL;
    int rc = sqlite3_open_v2(db_path, &db,
                             SQLITE_OPEN_READONLY | SQLITE_OPEN_NOMUTEX,
                             NULL);
    if (rc != SQLITE_OK || db == NULL) {
        fprintf(stdout, "{\"total_scanned_rows\": null, \"error\": \"%s\"}\n",
                db ? sqlite3_errmsg(db) : "out of memory");
        if (db) sqlite3_close(db);
        return 1;
    }

#if PROBE_SQL_TIMEOUT_SECONDS > 0
    signal(SIGALRM, timeout_handler);
    alarm(PROBE_SQL_TIMEOUT_SECONDS);
#endif

    /* Prepare */
    sqlite3_stmt *stmt = NULL;
    rc = sqlite3_prepare_v2(db, sql, -1, &stmt, NULL);
    if (rc != SQLITE_OK) {
        fprintf(stdout, "{\"total_scanned_rows\": null, \"error\": \"%s\"}\n",
                sqlite3_errmsg(db));
        sqlite3_close(db);
        return 1;
    }

    /* Execute fully: sqlite3_step until done or error */
    int step_rc = SQLITE_OK;
    while ((step_rc = sqlite3_step(stmt)) == SQLITE_ROW) {
        /* drain result set */
    }
    if (step_rc != SQLITE_DONE) {
        const char *err = sqlite3_errmsg(db);
        if (timed_out) {
            err = "SQL execution timed out";
        }
        fprintf(stdout,
                "{\"total_scanned_rows\": null, \"error\": \"%s\"}\n",
                err ? err : "unknown step error");
        sqlite3_finalize(stmt);
        sqlite3_close(db);
        return 1;
    }

#if PROBE_SQL_TIMEOUT_SECONDS > 0
    alarm(0);
#endif

    /* Collect real scanned rows via NVISIT */
    sqlite3_int64 total_nvisit = collect_nvisit(stmt);
    if (total_nvisit < 0) {
        fprintf(stdout,
                "{\"total_scanned_rows\": null, "
                "\"error\": \"scanstatus unavailable\"}\n");
        sqlite3_finalize(stmt);
        sqlite3_close(db);
        return 1;
    }

    fprintf(stdout,
            "{\"total_scanned_rows\": %lld, \"kind\": \"sqlite_stmt_scanstatus_v2_nvisit\"}\n",
            (long long)total_nvisit);

    sqlite3_finalize(stmt);
    sqlite3_close(db);
    return 0;
}
