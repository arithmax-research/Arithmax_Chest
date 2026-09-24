/ 1. Execute Python code using PyKX
\l pykx.q
.pykx.pyexec"
import pandas as pd
from achest import MarketDataClient

client = MarketDataClient('https://achestv2.misango.me')
raw = client.get(['AAPL'], '2026-09-01', '2026-09-23', 'daily' '', provider='yahoo')
client.close()

df = pd.DataFrame(raw)
df['time'] = pd.to_datetime(df['timestamp'])
for col in ['open', 'high', 'low', 'close', 'volume']: 
    df[col] = df[col].astype(float)
df = df.drop(columns=['time'])
";

/ 2. Bring into kdb+ space and convert
tbl: .pykx.toq .pykx.get `df;

/ ── Alternatively, pure q (no pykx needed) ───────────────────
/   \l achest.q
/ Then:
/   .achest.get[`AAPL; 2026.09.01; 2026.09.23; `daily]
/   .achest.providers[]
/   .achest.route[`AAPL;`daily;`auto]
/ ──────────────────────────────────────────────────────────────


/ 4. Render the table in VSCode
tbl;