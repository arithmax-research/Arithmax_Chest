\l achest-kdb-q/achest.q

/ 1. Start the daemon cleanly in the background
system "python3 achest-kdb-q/achest_daemon.py &"
.achest.setBackend[`daemon];
t1:.z.p;

/ 2. Run your fetch operations
payload: .achest.mkpayload[`AAPL; 2000.01.01; 2026.10.01; `daily; `auto];
raw_string: .achest.curlpost[payload; ""; "http://localhost:9999/v1/data"];
tbl_daemon: value raw_string;

/ 3. Print your benchmarking metrics
-1 "  fetch: ", string[`long\$((.z.p-t1)%1000000)], " ms";
-1 "  rows:  ", string count tbl_daemon;
meta tbl_daemon
tbl_daemon
/ 4. CLEAN UP: Safely target and kill whatever is running on port 9999
system "kill -9 \$(lsof -t -i:9999) 2>/dev/null || true";
-1 "Daemon process on port 9999 cleanly terminated.";
