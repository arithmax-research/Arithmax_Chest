/ Attempt to fetch option chain for a surface 
\l achest-kdb-q/achest.q

system "python3 achest-kdb-q/achest_daemon.py &"
.achest.setBackend[`daemon];

/ Fetch the clean IV surface
res:.achest.eulerIVSurface["AAPL"];
/ or: res:ivSurface["AAPL"];

/ ── For your 3D surface plotter ──
x:res`strikes       / strikes (only those with data)
y:res`daysToExpiry  / days to expiry (only those with data)
z:res`surface       / float matrix [rows×cols] — IV values, all non-null

/ ── For scatter plotting (strike, dte, iv) triples ──
t:res`table         / q table: ([ strike; dte; iv ])
/ Each row is one valid (strike, daysToExpiry, impliedVol) triple
