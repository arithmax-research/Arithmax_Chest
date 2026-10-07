/ ipc_bench.q - simple benchmark
\l achest-kdb-q/achest.q

host:`$[0=count .z.x;`13.212.15.78;`$.z.x 0]
port:$[1>count .z.x;5001;"I"$.z.x 1]
sym:$[2>count .z.x;`BTCUSDT;`$.z.x 2]
st:$[3>count .z.x;2026.10.01;value .z.x 3]
en:$[4>count .z.x;2026.10.06;value .z.x 4]
res:$[5>count .z.x;`daily;`$.z.x 5]

-1 "--- HTTP ---"
t0:.z.p;tbl:.achest.fetch[sym;st;en;res;()!()]
-1 "  ",string[`long$(.z.p-t0)%1000000]," ms  rows:",string count tbl

-1 "--- IPC (cold then warm, persistent connection) ---"
h:.achest.ipcConnect[host;port]
t0:.z.p;tbl:h (`fetch;sym;st;en;string res;string"auto")
cold:.z.p-t0
t0:.z.p;tbl:h (`fetch;sym;st;en;string res;string"auto")
warm:.z.p-t0
.achest.ipcClose[h]
-1 "  cold: ",string[`long$(cold%1000000)]," ms rows:",string count tbl
-1 "  warm: ",string[`long$(warm%1000000)]," ms rows:",string count tbl