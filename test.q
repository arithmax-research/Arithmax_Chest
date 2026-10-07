\l achest-kdb-q/achest.q

/ Connect and fetch via IPC — using strings for res/prov (matching HTTP API types)
h:.achest.ipcConnect[`13.212.15.78;5001]
-1 "handle: ", string[h];

/ The HTTP API sends res/prov as strings, try that over IPC too:
tbl:h (`fetch; enlist `BTCUSDT; 2026.09.01; 2026.10.06; "daily"; "auto")
-1 "rows: ", string count tbl;
meta tbl

.achest.ipcClose[h]