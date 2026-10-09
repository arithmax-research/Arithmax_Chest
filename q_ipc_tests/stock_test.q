\l achest-kdb-q/achest.q
.achest.setBackend[`http];
-1 "═══ Stocks: AAPL via HTTP (port 8001) ═══";
t2:.z.p
tbl:.achest.fetch[`AAPL; 2000.01.01; 2026.10.01; `daily; ()!()]
-1 "  fetch: ", string[`long$((.z.p-t2)%1000000)], " ms";
-1 "  type:  ", string type tbl;
-1 "  rows:  ", string count tbl;
meta tbl
tbl

\l achest-kdb-q/achest.q
.achest.setBackend[`daemon]    / ← switches from HTTPS to daemon

/ Now fetch — daemon already has a warm httpx pool to the server
tbl:.achest.fetch[`AAPL; 2000.01.01; 2026.10.01; `daily]

