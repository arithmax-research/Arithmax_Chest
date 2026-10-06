/ export QLIC=/home/ubuntu/.kx
/ nohup /home/ubuntu/.kx/bin/q achest-kdb-q/qserver_proxy.q -p 5001 < /dev/null > /tmp/qproxy.log 2>&1 &
/ sleep 2
/sample code
h:hopen `:localhost:5001
r:h(`fetch; `BTCUSDT; 2026.09.01; 2026.09.03; `daily; `auto)
tbl:value raze read0 `$":",r
count tbl
meta tbl