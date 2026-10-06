\l /Users/misango/codechest/achest/achest-kdb-q/achest.q
h:.achest.ipcConnect[`ec2-13-212-15-78.ap-southeast-1.compute.amazonaws.com; 5001]
tbl:.achest.ipcFetch[h; `BTCUSDT; 2026.09.01; 2026.10.06; `second]
.achest.ipcClose[h]
