/ ── 1. Fetch raw multi-asset data via Python ─────────────────
p)from achest import MarketDataClient
p)client = MarketDataClient()
p)raw = client.get(["AAPL","MSFT","BTCUSDT"], "2026-09-01", "2026-09-21", "daily")
p)client.close()

/ ── 2. FIX: Pull global Python object directly by its symbol ──
/ This bypasses the evaluation wrapper error completely
tbl: .pykx.toq .pykx.get `raw

/ ── 3. Clean up the types without using backslashes ─────────
tbl: update
  time:   "D"$string timestamp,
  open:   "F"$string open,
  high:   "F"$string high,
  low:    "F"$string low,
  close:  "F"$string close,
  volume: "J"$string volume
  from tbl

/ Sort and apply attribute for downstream asof joins (aj)
tbl: `time xasc tbl
tbl: update `g#symbol from tbl

/ ── 4. Verify types and split ────────────────────────────────
meta tbl
aapl: select from tbl where symbol = `AAPL

/ ── 5. Run your moving average ───────────────────────────────
aapl_ma: select time, close, ma2: mavg[2;close], ma5: mavg[5;close] from aapl
