/ achest.q — native kdb+/q client for the Arithmax Chest API
/ ───────────────────────────────────────────────────────────────────
/ Usage:
/   \l achest.q
/   .achest.fetch[`BTCUSDT; 2026.09.01; 2026.09.23; `minute]
/   .achest.fetch[`BTCUSDT; 2026.09.01; 2026.09.23; `minute; (`provider`token)!(`massive;`abc123)]
/   .achest.providers[]              / list providers
/   .achest.route[`AAPL;`daily;`auto] / route symbol
/   achestFetch[`BTCUSDT; 2026.09.01; 2026.09.23; `minute]  / root alias
/
/ ── Transport backends ─────────────────────────────────────────
/   .achest.setBackend[`curl]     — HTTPS via Caddy (works anywhere)
/   .achest.setBackend[`http]     — HTTP direct to FastAPI (no TLS, needs port 8001 open)
/   .achest.setBackend[`daemon]   — persistent keepalive via achest_daemon.py (fastest)
/
/   .achest.setBackend[`http]     / switch after loading
/
/ ── Fastest setup (recommended) ──
/   1. Ensure port 8001 is open on the server
/   2. In a terminal: python3 achest-kdb-q/achest_daemon.py &
/   3. In q: .achest.setBackend[`daemon]
/   4. Fetch normally

/ Check curl is available
if[0N~@[system;"which curl 2>/dev/null";0N];
  -2 "ERROR: achest.q requires curl on PATH";
  exit 1]

\d .achest

/ ── Configuration ──────────────────────────────────────────────────
HTTPS_URL:"https://achestv2.misango.me"      / Caddy (TLS, works anywhere)
HTTP_URL:"http://46.225.46.174:8001"          / FastAPI direct (no TLS, fast)
TOKEN:getenv`DATA_API_TOKEN                   / defaults to ""
BACKEND:`curl                                 / current transport
DAEMON_HOST:`localhost
DAEMON_PORT:9999

/ Switch transport backend at runtime.
setBackend:{[b]
  if[not b in `curl`http`daemon; '"achest: unknown backend: ",string b];
  BACKEND::b;
  b }

/ Resolve active base URL for the current backend.
baseUrl:{[]
  $[BACKEND~`http;  HTTP_URL;
    BACKEND~`daemon; "http://",string[DAEMON_HOST],":",string DAEMON_PORT;
    HTTPS_URL] }

/ ── Build JSON payload via .j.j ──────────────────────
mkpayload:{[syms;st;en;res;prov]
  / 1. Fix symbol list coercion
  syms:$[-11h=type syms; enlist string syms;           
         11h=type syms; string syms;                   
         10h=type syms; enlist syms;                   
         syms];                                        
  
  / 2. Fix date/timestamp serialization to ISO 8601 (YYYY-MM-DD)
  fmt: {$[10h=type x; x;                                            / if already string, leave alone
          type[x] in -12 -14 -15h; [s:string x; s[4 7]:"-"; ssr[s;"D";"T"]]; / format dates & timestamps
          string x]};                                               / fallback

  .j.j `symbols`start`end`resolution`provider`format!
        (syms;fmt st;fmt en;string[res];string[prov];`q)
 }
/ ── curl POST (temp file payload, socket output — fast I/O) ──
curlpost:{[payload;token;url]
  auth:$[""~token; ""; " -H 'Authorization: Bearer ",token,"'"];
  fn:"/tmp/_qp_",string .z.i;
  (`$":",fn) 0: enlist payload;
  rfn:"/tmp/_qr_",string .z.i;
  cmd:"curl -s --max-time 600 --compressed --keepalive-time 60",
      auth,
      " -H 'Content-Type: application/json'",
      " -X POST -d @",fn," '",url,"' > ",rfn," 2>&1 || true";
  @[system;cmd;0N];
  @[system;"rm -f ",fn;0N];
  r:@[read0; `$":",rfn; {""}];
  @[system;"rm -f ",rfn;0N];
  if[0h=type r; r:raze r];
  if[not 10h=type r; r:""];
  if["curl: ("~9#r; '"curl: ",r];
  :r }

/ ── Core single-request fetch (no parallelism) ──────────
fetchSingle:{[syms;st;en;res;opts]
  prov:$[`provider in key opts; opts`provider; `auto];
  token:$[`token in key opts; opts`token; TOKEN];
  url:baseUrl[],"/v1/data";
  raw:curlpost[mkpayload[syms;st;en;res;prov];token;url];
  @[value;raw;{'"achest: parse failed: ",x,"\nraw:\n",y}[;raw]]
 }

/ ── Public: fetch market data ──────────────────────────
/   Options: chunks=N  — split date range into N parallel sub-queries
/            parallel=0b — disable multi-symbol parallel
fetch:{[syms;st;en;res;opts]
  o:$[99h=type opts; opts; (enlist`provider)!enlist` ];
  chunks:$[`chunks in key o; o`chunks; 1];
  / ═══ 1) Date-range chunking (split large ranges into parallel pieces) ═══
  if[chunks>1;
    days:("i"$en)-"i"$st;
    if[days<chunks; chunks:1|days];               / cap chunks at number of days
    step:1|days div chunks;                        / days per chunk (minimum 1)
    edges:st+step*til 1+chunks;                    / boundary dates
    edges[chunks]:en;                              / ensure last boundary = end date
    :raze {[se] .achest.fetchSingle[syms;se 0;se 1;res;o,enlist[`chunks]!1]}
          peach flip (edges til chunks; edges 1+til chunks)
    ];
  / ═══ 2) Multi-symbol parallel (each symbol fetched in its own process) ═══
  parallel:$[`parallel in key o; o`parallel; 11h=type syms];
  if[parallel and 11h=type syms;
    :raze .achest.fetchSingle[;st;en;res;o] peach syms
    ];
  / ═══ 3) Single request ═══
  .achest.fetchSingle[syms;st;en;res;o]
 }

/ ── 4-arg shorthand ─────────────────────────────────
fetch4:{[syms;st;en;res] .achest.fetch[syms;st;en;res;()!()] }

/ ── Direct q IPC fetch (not available — blocked by KX license) ──
/   q's `hopen` to remote hosts is blocked by the KX license daemon
/   (`'license error: daemon returned error 'blocked`). IPC cannot
/   be used. Use `.achest.setBackend[`http]` or `daemon` instead.
/ ─────────────────────────────────────────────────────────────────
ipcConnect:{[host;port]
  h:hopen `$ (":" , (string host) , ":" , (string port));
  if[h<=0; '"ipc: cannot connect to ",host,":",string port];
  h }

ipcFetch:{[h;syms;st;en;res;prov]
  p:$[`~prov; `auto; prov];
  / The server now returns the table directly over the wire
  h (`fetch; syms; st; en; res; p)
 }                / if server signaled an error  

ipcClose:{[h] hclose h; }

/ One-shot: connect, fetch, close (supports 6 or 7 args)
ipc:{[host;port;syms;st;en;res;prov]
  if[`~prov; prov:`auto];
  h:.[.achest.ipcConnect; (host;port); {'"ipc connect failed: ",x}];
  r:.[.achest.ipcFetch; (h; syms; st; en; res; prov); {'"ipc fetch failed: ",x}];
  .[.achest.ipcClose; enlist h; {0N}];
  r }




/ ── List providers ───────────────────────────────────
providers:{[]
  auth:$[""~TOKEN; ""; " -H 'Authorization: Bearer ",TOKEN,"'"];
  raw:@[system;
    "curl -s",auth," '",baseUrl[],"/v1/providers'";
    {'"achest: curl failed: ",x}];
  @[value;raw;{'"achest: parse failed: ",x}] }

/ ── Route symbol ─────────────────────────────────────
route:{[sym;res;prov]
  auth:$[""~TOKEN; ""; " -H 'Authorization: Bearer ",TOKEN,"'"];
  raw:@[system;
    "curl -s",auth," '",baseUrl[],"/v1/route?symbol=",string[sym],"&resolution=",string[res],"&provider=",string[prov],"'";
    {'"achest: curl failed: ",x}];
  @[value;raw;{'"achest: parse failed: ",x}] }

\d .

/ ── Root-level alias for easier VS Code use ──────────
if[not `achestFetch in key `;
  achestFetch:{[s;st;en;res] .achest.fetch4[s;st;en;res]}]
