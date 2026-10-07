\l achest-kdb-q/achest.q

-1 "== HTTP ==";
t2:.z.p;tbl:.achest.fetch[`BTCUSDT;2026.10.01;2026.10.06;`daily;()!()]
-1 "  ",string[`long$((.z.p-t2)%1000000)]," ms  type:",string type tbl," rows:",string count tbl;

-1 "== IPC ==";
t2:.z.p;h:.achest.ipcConnect[`13.212.15.78;5001]
tbl:h (`fetch;`BTCUSDT;2026.10.01;2026.10.06;"daily";"auto")
.achest.ipcClose[h]
-1 "  ",string[`long$((.z.p-t2)%1000000)]," ms  type:",string type tbl," rows:",string count tbl;

meta tbl