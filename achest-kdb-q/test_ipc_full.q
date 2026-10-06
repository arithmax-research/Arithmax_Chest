/ test_ipc_full.q — test the direct q IPC proxy end-to-end
/ usage: q test_ipc_full.q -p 0

h:hopen `:localhost:5001;
if[h<=0; show "FAIL: cannot connect to proxy"; exit 1];

rfn:h(`fetch; `BTCUSDT; 2026.09.01; 2026.09.03; `daily; `auto);
if[-11h=type rfn; show "FAIL: proxy error: ",string rfn; hclose h; exit 1];

show "filename received: ",rfn;

lines:read0 `$":",rfn;
show "lines read: ",string count lines;

raw:raze lines;
show "total chars: ",string count raw;

tbl:value raw;
show "rows: ",string count tbl;
show "columns: ",string cols tbl;
meta tbl;

@[system;"rm -f ",rfn;0N];
hclose h;
show "DONE";

exit 0;