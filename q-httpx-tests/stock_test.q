\l achest-kdb-q/achest.q
.achest.setBackend[`http];
-1 "═══ 1. HTTP Backend ═══";
t1:.z.p;
tbl_http:.achest.fetch["AAPL"; 2000.01.01; 2026.10.01; `daily; ()!()];
-1 "  fetch: ", string[`long$((.z.p-t1)%1000000)], " ms";
-1 "  rows:  ", string count tbl_http;
tbl_http
meta tbl_http