/ bench.q — benchmark: HTTP vs direct HTTP vs daemon backends
\\l achest-kdb-q/achest.q

sym:`$[2>count .z.x;`BTCUSDT;`$.z.x 2]
st:$[3>count .z.x;2026.10.01;value .z.x 3]
en:$[4>count .z.x;2026.10.06;value .z.x 4]
res:$[5>count .z.x;`daily;`$.z.x 5]

-1 "═══ Backend: curl (HTTPS via Caddy/TLS) ═══";
.achest.setBackend[`curl];
t0:.z.p;tbl:.achest.fetch[sym;st;en;res;()!()];
-1 "  ",string[`long$(.z.p-t0)%1000000]," ms  rows:",string count tbl;

-1 "═══ Backend: http (HTTP direct port 8001, no TLS) ═══";
.achest.setBackend[`http];
t0:.z.p;tbl:.achest.fetch[sym;st;en;res;()!()];
-1 "  ",string[`long$(.z.p-t0)%1000000]," ms  rows:",string count tbl;

-1 "═══ Backend: daemon via curl (local, persistent pool) ═══";
.achest.setBackend[`daemon];
t0:.z.p;tbl:.achest.fetch[sym;st;en;res;()!()];
-1 "  ",string[`long$(.z.p-t0)%1000000]," ms  rows:",string count tbl;