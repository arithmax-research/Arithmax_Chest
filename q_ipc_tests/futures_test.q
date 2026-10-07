\l achest-kdb-q/achest.q
-1 "═══ IPC (via q proxy) ═══";
t2:.z.p
h:.achest.ipcConnect[`13.212.15.78;5001]
tbl_ipc_esfut:h (`fetch; `ES.FUT; 2026.01.01; 2026.10.01; "daily"; "auto")
-1 "  fetch: ", string[`long$((.z.p-t2)%1000000)], " ms";
-1 "  type:  ", string type tbl_ipc_esfut;
-1 "  rows:  ", string count tbl_ipc_esfut;
meta tbl_ipc_esfut
tbl_ipc_esfut
.achest.ipcClose[h]