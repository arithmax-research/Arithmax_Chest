\l achest-kdb-q/achest.q

/ HTTP direct to FastAPI port 8001 (no TLS, needs port 8001 open)
.achest.setBackend[`http];

-1 "═══ Index: ^VIX via HTTP (port 8001) ═══";
t2:.z.p
tbl:.achest.fetch[`$"^VIX"; 2026.01.01; 2026.10.07; `daily; ()!()]
-1 "  fetch: ", string[`long$((.z.p-t2)%1000000)], " ms";
-1 "  type:  ", string type tbl;
-1 "  rows:  ", string count tbl;
meta tbl
tbl