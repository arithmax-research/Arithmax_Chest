\l achest-kdb-q/achest.q

/ IPC fetch via q server proxy (13.212.15.78:5001)
h:.achest.ipcConnect[`13.212.15.78;5001]

/ The proxy handles type conversion internally
/ Bare symbol for syms → auto-stringified & enlisted by the proxy
tbl:h (`fetch; `BTCUSDT; 2026.09.01; 2026.10.06; "daily"; "auto")

-1 "rows: ", string count tbl;
meta tbl

.achest.ipcClose[h]