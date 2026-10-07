\l achest-kdb-q/achest.q
-1 "═══ IPC (via q proxy) ═══";
t2:.z.p
h:.achest.ipcConnect[`13.212.15.78;5001]
tbl_ipc_esfut:h (`fetch; `ES.FUT; 2026.01.01; 2026.10.07; "daily"; "auto")
-1 "  fetch: ", string[`long$((.z.p-t2)%1000000)], " ms";
-1 "  type:  ", string type tbl_ipc_esfut;
-1 "  rows:  ", string count tbl_ipc_esfut;
type_id: type tbl_ipc_esfut;
type_name: $[
    type_id = 98h;  "Table";
    type_id = 99h;  "Dictionary / Keyed Table";
    type_id = 101h; "Unary Primitive (likely generic null '::')";
    type_id = 0h;   "Mixed List";
    type_id > 0h;   "List of type ", string type_id;
    "Atom of type ", string abs type_id
 ];

-1 "=== Data Inspection ===";
-1 "Numeric Type ID: ", string type_id;
-1 "Human Readable: ", type_name;
-1 "Raw Content:    ", .Q.s1 tbl_ipc_esfut;
meta tbl_ipc_esfut
type tbl_ipc_esfut
tbl_ipc_esfut
.achest.ipcClose[h]