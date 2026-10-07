\l achest-kdb-q/achest.q

h:.achest.ipcConnect[`13.212.15.78;5001]
tbl:.achest.ipcFetch[h;`BTCUSDT;2026.09.01;2026.10.06;`daily;`auto]
.achest.ipcClose[h]

count tbl
meta tbl
tbl