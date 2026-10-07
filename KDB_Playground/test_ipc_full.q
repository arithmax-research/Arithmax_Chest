\l achest-kdb-q/achest.q
h: .achest.ipcConnect[`localhost; 5001]
tbl: .achest.ipcFetch[h; `BTCUSDT; 2026.09.01; 2026.10.06; `daily; `auto]
.achest.ipcClose[h]
