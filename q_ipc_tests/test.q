\l achest-kdb-q/achest.q

-1 "== HTTP ==";
t0:.z.p;tbl:.achest.fetch[`BTCUSDT;2026.10.01;2026.10.06;`daily;()!()]
-1 "  time:",string[`long$((.z.p-t0)%1000000)],"ms  type:",string type tbl," rows:",string count tbl;

-1 "== IPC ==";
t0:.z.p;h:.achest.ipcConnect[`13.212.15.78;5001]
tbl:h (`fetch;`BTCUSDT;2026.10.01;2026.10.06;"daily";"auto")
.achest.ipcClose[h]
-1 "  time:",string[`long$((.z.p-t0)%1000000)],"ms  type:",string type tbl," rows:",string count tbl;

meta tbl