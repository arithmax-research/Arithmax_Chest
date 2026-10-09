\\l achest-kdb-q/achest.q

/ A) HTTP via Caddy/TLS (default backend — works everywhere)
-1 "═══ Backend: curl (HTTPS via Caddy/TLS) ═══";
.achest.setBackend[`curl];
t2:.z.p
tbl_http:.achest.fetch[`BTCUSDT; 2026.10.01; 2026.10.06; `daily; ()!()]
-1 "  fetch: ", string[`long$((.z.p-t2)%1000000)], " ms";
-1 "  type:  ", string type tbl_http;
-1 "  rows:  ", string count tbl_http;
meta tbl_http

/ B) HTTP direct to FastAPI port 8001 (no TLS, needs port 8001 open)
-1 "═══ Backend: http (direct to port 8001) ═══";
.achest.setBackend[`http];
t2:.z.p
tbl_http:.achest.fetch[`BTCUSDT; 2026.10.01; 2026.10.06; `daily; ()!()]
-1 "  fetch: ", string[`long$((.z.p-t2)%1000000)], " ms";
-1 "  type:  ", string type tbl_http;
-1 "  rows:  ", string count tbl_http;
meta tbl_http
tbl_http
