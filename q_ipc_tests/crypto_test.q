\l achest-kdb-q/achest.q


/ A) HTTP — direct to API
-1 "═══ HTTP (via achest.q) ═══";
t2:.z.p
tbl_http:.achest.fetch[`BTCUSDT; 2026.10.01; 2026.10.06; `daily; ()!()]
-1 "  fetch: ", string[`long$((.z.p-t2)%1000000)], " ms";
-1 "  type:  ", string type tbl_http;
-1 "  rows:  ", string count tbl_http;
meta tbl_http

/ B) IPC — via q proxy
-1 "═══ IPC (via q proxy) ═══";
t2:.z.p
h:.achest.ipcConnect[`13.212.15.78;5001]
tbl_ipc:h (`fetch; `BTCUSDT; 2020.10.01; 2026.10.01; "daily"; "auto")
-1 "  fetch: ", string[`long$((.z.p-t2)%1000000)], " ms";
-1 "  type:  ", string type tbl_ipc;
-1 "  rows:  ", string count tbl_ipc;
meta tbl_ipc
tbl_ipc
.achest.ipcClose[h]
