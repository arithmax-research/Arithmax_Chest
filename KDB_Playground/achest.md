Here's the full end-to-end `achest.q` workflow, step by step:

---

## 🔄 `achest.q` Workflow — End to End

### Step 0: The File

**Location:** `achest-kdb-q/achest.q` (82 lines of pure q)

It's a self-contained q script with **no dependencies except `curl`** on the system PATH.

---

### Step 1: Load the Client

```q
\l achest-kdb-q/achest.q
```

**What happens at load time:**

**① Curl check** (line 12–14):
```q
if[0N~@[system;"which curl 2>/dev/null";0N];
  -2 "ERROR: achest.q requires curl on PATH";
  exit 1]
```
Protected evaluation (`@[system; ...; 0N]`) tries to run `which curl`. If it fails (`0N`), the script prints an error and exits. **If curl is missing, you get a clear message instead of a cryptic failure later.**

**② Switch namespace** (line 16):
```q
\d .achest
```
All functions are defined in the `.achest` namespace to avoid polluting the root.

**③ Set configuration** (line 18–19):
```q
BASE_URL:"https://achestv2.misango.me"
TOKEN:getenv`DATA_API_TOKEN
```
- `BASE_URL` — the hosted API endpoint (configurable if self-hosting)
- `TOKEN` — reads the `DATA_API_TOKEN` environment variable (empty string if unset)

**④ Define `mkpayload`** (lines 22–36) — the JSON payload builder.

**⑤ Define `curlpost`** (lines 38–48) — the HTTP transport.

**⑥ Define `fetch`** (lines 51–57) — the main public function.

**⑦ Define `fetch4`** (line 60) — a 4-argument shorthand.

**⑧ Define `providers`** (lines 63–68) — list available data providers.

**⑨ Define `route`** (lines 71–76) — inspect symbol routing.

**⑩ Return to root namespace** (line 78):
```q
\d .
```

**⑪ Create root alias** (lines 81–82):
```q
if[not `achestFetch in key `;
  achestFetch:{[s;st;en;res] .achest.fetch4[s;st;en;res]}]
```
Creates `achestFetch` in the root namespace for convenience (easier to type in VS Code's kdb extension without namespace prefixes).

---

### Step 2: Fetch Data

```q
tbl: .achest.fetch[`BTCUSDT; 2026.09.01; 2026.09.23; `minute; ()!()]
```

This calls `fetch` with **5 arguments** (symbols, start, end, resolution, options dictionary):

#### Inside `fetch` (lines 51–57):

```q
fetch:{[syms;st;en;res;opts]
  o:$[99h=type opts; opts; (enlist`provider)!enlist` ];    // [A]
  prov:$[`provider in key o; o`provider; `auto];            // [B]
  token:$[`token in key o; o`token; TOKEN];                 // [C]
  raw:curlpost[mkpayload[syms;st;en;res;prov];token];       // [D]
  @[value;raw;{'..."achest: parse failed: ..."}[;raw]]      // [E]
 }
```

**[A]** — If `opts` is already a dictionary (`99h`), use it; otherwise create a default empty dictionary.
**[B]** — Extract `provider` from options, defaulting to `` `auto ``.
**[C]** — Extract `token` from options, defaulting to the env var `DATA_API_TOKEN`.
**[D]** — Build the payload and POST it.
**[E]** — `value` parses the JSON response string into a native q table. If parsing fails, it throws a descriptive error showing both the error and the raw response.

---

### Step 3: Build the Payload (`mkpayload`, lines 22–36)

```q
mkpayload:{[syms;st;en;res;prov]
  syms:$[-11h=type syms; enlist string syms;
         11h=type syms; string syms;
         10h=type syms; enlist syms;
         syms];

  fmt: {$[10h=type x; x;
          type[x] in -12 -14 -15h; [s:string x; s[4 7]:"-"; ssr[s;"D";"T"]];
          string x]};

  .j.j `symbols`start`end`resolution`provider`format!
        (syms;fmt st;fmt en;string[res];string[prov];`q)
 }
```

**Symbol normalization** — Handles all the ways a user might pass symbols:

| User passes | Type (`type`) | Result |
|------------|--------------|--------|
| `` `BTCUSDT `` | `-11h` (symbol atom) | `enlist "BTCUSDT"` → `["BTCUSDT"]` |
| `` `BTCUSDT`ETHUSDT `` | `11h` (symbol list) | `("BTCUSDT";"ETHUSDT")` |
| `"BTCUSDT"` | `10h` (string) | `enlist "BTCUSDT"` → `["BTCUSDT"]` |

**Date formatting** — q dates (`2026.09.01`) are `-14h` type. Their `string` representation is `"2026-09-01"` (with hyphens). But q timestamps (`-15h` / `-12h`) like `2026.09.01D12:00:00.000` stringify to `"2026-09-01D12:00:00.000000000"`. The `fmt` function:
- Replaces hyphens at positions 4 and 7 with nothing (they're already correct for dates)
- Replaces `D` with `T` to get ISO 8601: `"2026-09-01T12:00:00.000000000"`

**Critical detail — `format`:\`q\`** — The payload includes `` `format`!`q `` which tells the server to **serialize the response as a q table literal** (via `to_q_table()` on the Python side). This is what makes the response directly `value`-able in q.

**Resulting JSON payload** (what gets sent to the server):
```json
{
  "symbols": ["BTCUSDT"],
  "start": "2026-09-01",
  "end": "2026-09-23",
  "resolution": "minute",
  "provider": "auto",
  "format": "q"
}
```

---

### Step 4: HTTP POST (`curlpost`, lines 38–48)

```q
curlpost:{[payload;token]
  auth:$[""~token; ""; " -H 'Authorization: Bearer ",token,"'"];
  cmd:"curl -s --max-time 120",
      auth,
      " -H 'Content-Type: application/json'",
      " -X POST -d '",payload,"' '",BASE_URL,"/v1/data'";
  r:@[system;cmd;{'..."achest: curl failed: ..."}];
  if[0h=type r; r:raze r];
  if[10h=type r; :r];
  '"achest: unexpected curl response type: ",string[type r]
 }
```

Builds the curl command:
```
curl -s --max-time 120
  -H 'Content-Type: application/json'
  -X POST -d '{...payload...}'
  'https://achestv2.misango.me/v1/data'
```

With optional `-H 'Authorization: Bearer <token>'` if a token is set.

- `-s` — silent mode (no progress bar)
- `--max-time 120` — 2-minute timeout for large historical queries
- Protected eval catches curl failures (network down, timeout, etc.)

`system` in q returns a **list of strings** (one per line). `raze` joins them into one string. If the result is already a string, it passes through.

---

### Step 5: Server-Side Processing (Python/FastAPI)

The server (`achest/server.py:116-120`) sees `format="q"` and calls `to_q_table()`:

```python
if request.format == "q":
    return Response(
        to_q_table(table, include_metadata=True),
        media_type="text/plain",
    )
```

`to_q_table()` (lines 557–597) does:

**① Rename `timestamp` → `time`** — q convention for temporal key column.

**② Drop metadata** unless `include_metadata=True` — the server always includes it (the q client can ignore extra columns).

**③ Serialize each column** as a q list literal:

| Python type | q literal | Example |
|------------|-----------|---------|
| `pd.Timestamp` | `2026.09.01D12:00:00.000000000` | q timestamp |
| `float` / `int` | `45000.5` | q float/int |
| `str` (symbol) | `` `AAPL `` | q symbol |
| `str` (other) | `"some string"` | q string |
| `NaN` | `0n` | q null float |

**Result:** A response like:
```
([] time:(2026.09.01D09:30:00.000000000; 2026.09.01D09:31:00.000000000; ...);
   open:(150.25; 150.30; ...);
   high:(151.00; 151.10; ...);
   low:(149.80; 149.90; ...);
   close:(150.50; 150.75; ...);
   volume:(1234567; 2345678; ...);
   symbol:(`AAPL; `AAPL; ...);
   provider:(`yahoo; `yahoo; ...))
```

---

### Step 6: Parse the Response Back in q

Back in `fetch` (line 56):
```q
@[value;raw;{...}]
```

**`value`** is q's built-in **parse/evaluate** function. It takes the string literal from the server and evaluates it as q code, producing a native q table directly:

```q
// raw (string):
"([] time:(2026.09.01D09:30:00.000000000; ...); open:(150.25; ...); ...)"

// after `value`:
tbl: `time`sym`open`high`low`close`volume!+`time`sym`open`high`low`close`volume!...

// You now have a real q table:
meta tbl
// ┌───────┬──────────┐
// │ col   │ type     │
// ├───────┼──────────┤
// │ time  │ timestamp│
// │ sym   │ symbol   │
// │ open  │ float    │
// │ high  │ float    │
// │ low   │ float    │
// │ close │ float    │
// │ volume│ float    │
// └───────┴──────────┘
```

---

### Step 7: Use the Data in q

Now `tbl` is a real q table. You can do everything:

```q
// First/last rows
first tbl
last tbl
count tbl

// OHLCV resampling to 1-hour bars
select open:first open, high:max high, low:min low, close:last close,
       volume:sum volume
  by time:1 xbar time.hour
  from tbl

// 20-period moving average
select close, mavg20:20 mavg close from tbl

// Daily returns
select time, close, ret:close % prev close - 1 from tbl

// Asof join with another table
aj[`time; tbl; otherTable]
```

---

### Step 8: Alternative Entry Points

**4-argument shorthand** (line 60):
```q
.achest.fetch4[`BTCUSDT; 2026.09.01; 2026.09.23; `minute]
// same as .achest.fetch[`BTCUSDT; 2026.09.01; 2026.09.23; `minute; ()!()]
```

**Root-level alias** (lines 81–82):
```q
achestFetch[`BTCUSDT; 2026.09.01; 2026.09.23; `minute]
// same as .achest.fetch4[...]
```

**With provider override:**
```q
.achest.fetch[`BTCUSDT; 2026.09.01; 2026.09.23; `minute; (`provider)!`massive]
```

**With custom token:**
```q
.achest.fetch[`BTCUSDT; 2026.09.01; 2026.09.23; `minute; (`token)!("my-token";)]
```

---

### Step 9: Utility Functions

**List providers** (`providers`):
```q
.achest.providers[]
// Returns: `yahoo`binance`massive`databento`alpaca`tiingo`alpha_vantage`fred`quandl`eulerpool
```

**Route a symbol** (`route`):
```q
.achest.route[`AAPL; `daily; `auto]
// Returns info about which provider will serve this symbol/resolution combo
```

---

## 📋 Visual Summary

```
┌─────────────────────────────────────────────────────────────────────┐
│                        USER'S Q SESSION                             │
│                                                                     │
│  \l achest.q                                                       │
│       │                                                             │
│       ├── Checks curl exists ────────────────────────── FAIL → exit │
│       │                                                             │
│       ├── Sets BASE_URL, reads DATA_API_TOKEN                       │
│       │                                                             │
│       └── Defines .achest.fetch, .achest.providers, .achest.route  │
│                                                                     │
│  tbl: .achest.fetch[`BTCUSDT; 2026.09.01; 2026.09.23; `minute]    │
│       │                                                             │
│       ├── fetch() parses opts, extracts provider/token              │
│       │                                                             │
│       ├── mkpayload() builds JSON with format="q"                   │
│       │   "symbols":["BTCUSDT"],"start":"2026-09-01",...            │
│       │                                                             │
│       ├── curlpost() runs:                                          │
│       │   curl -s -X POST -d '{...}'                                │
│       │     https://achestv2.misango.me/v1/data                     │
│       │                                                             │
│       │                      │  HTTP POST                           │
│       │                      ▼                                      │
│       │         ┌──────────────────────────────────┐                │
│       │         │     FastAPI Server (Python)       │               │
│       │         │                                  │                │
│       │         │  1. Route symbol → pick provider  │               │
│       │         │  2. Fetch from upstream (Yahoo,   │               │
│       │         │     Binance, Massive, etc.)       │               │
│       │         │  3. Normalize to OHLCV DataFrame  │               │
│       │         │  4. format="q" → to_q_table()     │               │
│       │         │     → q table literal string      │               │
│       │         └──────────────────────────────────┘                │
│       │                      │  HTTP 200                            │
│       │                      ▼                                      │
│       │                                                             │
│       └── value(raw) → parses q literal → native q table           │
│                                                                     │
│  tbl is now a real q table — ready for asof joins,                  │
│  moving windows, resampling, or splaying to disk.                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🎯 Key Design Decisions

| Decision | Why |
|----------|-----|
| **Uses `curl` instead of q's built-in HTTP** | q's `.Q.hg`/`.Q.hp` vary across versions; `curl` is universally available and handles TLS, timeouts, and large payloads reliably |
| **Sends `format":"q"` in the payload** | The server serializes as a q literal, so the client just calls `value` — no manual JSON parsing in q |
| **`@[value; raw; {...}]` protected eval** | If the server returns an error message (not valid q), the user gets a clear error with the raw response for debugging |
| **`fetch4` + `achestFetch` alias** | Reduces typing for the most common use case; the root alias is especially helpful in VS Code's kdb extension where you can't type namespace prefixes easily |
| **Environment variable for token** | Follows q conventions; keeps secrets out of scripts |

---

## 🧪 In Practice (from `native_test.q`)

```q
\l achest-kdb-q/achest.q
tbl: .achest.fetch[`BTCUSDT; 2026.09.22; 2026.09.23; `minute; ()!()]
\c 2000 10000    // widen the console for display
tbl              // see the data
```

That's it. **Two lines of q** to get multi-provider, normalized market data into a native q table.