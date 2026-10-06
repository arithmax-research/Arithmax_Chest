/ achest.q — native kdb+/q client for the Arithmax Chest API
/ ───────────────────────────────────────────────────────
/ Usage:
/   \l achest.q
/   .achest.fetch[`BTCUSDT; 2026.09.01; 2026.09.23; `minute]
/   .achest.fetch[`BTCUSDT; 2026.09.01; 2026.09.23; `minute; (`provider`token)!(`massive;`abc123)]
/   .achest.providers[]              / list providers
/   .achest.route[`AAPL;`daily;`auto] / route symbol
/   achestFetch[`BTCUSDT; 2026.09.01; 2026.09.23; `minute]  / root alias

/ Check curl is available
if[0N~@[system;"which curl 2>/dev/null";0N];
  -2 "ERROR: achest.q requires curl on PATH";
  exit 1]

\d .achest

BASE_URL:"https://achestv2.misango.me"
TOKEN:getenv`DATA_API_TOKEN       / defaults to "" if env var not set

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
/ ── curl POST (payload via temp file — avoids shell quoting issues) ──
curlpost:{[payload;token]
  auth:$[""~token; ""; " -H 'Authorization: Bearer ",token,"'"];
  fn:"/tmp/_qpayload_",string .z.i;              / unique temp file per PID
  (`$":",fn) 0: enlist payload;                    / write JSON payload to file
  cmd:"curl -s --max-time 600 --compressed --keepalive-time 60",
      auth,
      " -H 'Content-Type: application/json'",
      " -X POST -d @",fn," '",BASE_URL,"/v1/data' 2>&1 || true";
  r:@[system;cmd;0N];                          / 0N = "command failed" sentinel
  if[0N~r; '"curl: command could not start\ncmd:\n",cmd];
  @[system;"rm -f ",fn;0N];                          / clean up temp file
  if[0h=type r; r:raze r];           / join list of lines into one string
  if[not 10h=type r; '"curl: unexpected response type: ",string[type r]];
  if["curl: ("~9#r; '"curl: ",r];                    / detect curl errors (timeout, DNS, etc.)
  :r }                                / return raw response

/ ── Core single-request fetch (no parallelism) ──────────
fetchSingle:{[syms;st;en;res;opts]
  prov:$[`provider in key opts; opts`provider; `auto];
  token:$[`token in key opts; opts`token; TOKEN];
  raw:curlpost[mkpayload[syms;st;en;res;prov];token];
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

/ ── Direct q IPC fetch (bypasses HTTP/curl) ──────────────
/   Connect to a q proxy on the server and fetch via native q IPC.
/   Usage:
/     h:.achest.ipcConnect[`aws-host;5001]
/     tbl:.achest.ipcFetch[h;`BTCUSDT;2026.09.01;2026.10.06;`second]
/     .achest.ipcClose[h]
/   Or with a helper:
/     tbl:.achest.ipc[`aws-host;5001;`BTCUSDT;2026.09.01;2026.10.06;`second]
/ ─────────────────────────────────────────────────────────
ipcConnect:{[host;port]
  h:hopen `$":",host,":",string port;
  if[h<=0; '"ipc: cannot connect to ",host,":",string port];
  h }

ipcFetch:{[h;syms;st;en;res;prov]
  prov:$[`~prov; `auto; prov];
  rfn:h (`fetch; syms; st; en; res; prov);
  if[-11h=type rfn; :'rfn];                / if server signaled an error
  fh:hopen `$":",rfn;                       / open response file
  r:value read(fh; hcount fh);              / read and parse
  hclose fh;
  @[system;"rm -f ",rfn;0N];               / clean up
  r }

ipcClose:{[h] hclose h; }

/ One-shot: connect, fetch, close
ipc:{[host;port;syms;st;en;res;prov]
  h:.achest.ipcConnect[host;port];
  r:@[.achest.ipcFetch[h;syms;st;en;res;prov];{.'"ipc: ",x}];
  .achest.ipcClose[h];
  r }

/ ── List providers ───────────────────────────────────
providers:{[]
  auth:$[""~TOKEN; ""; " -H 'Authorization: Bearer ",TOKEN,"'"];
  raw:@[system;
    "curl -s",auth," '",BASE_URL,"/v1/providers'";
    {'"achest: curl failed: ",x}];
  @[value;raw;{'"achest: parse failed: ",x}] }

/ ── Route symbol ─────────────────────────────────────
route:{[sym;res;prov]
  auth:$[""~TOKEN; ""; " -H 'Authorization: Bearer ",TOKEN,"'"];
  raw:@[system;
    "curl -s",auth," '",BASE_URL,"/v1/route?symbol=",string[sym],"&resolution=",string[res],"&provider=",string[prov],"'";
    {'"achest: curl failed: ",x}];
  @[value;raw;{'"achest: parse failed: ",x}] }

\d .

/ ── Root-level alias for easier VS Code use ──────────
if[not `achestFetch in key `;
  achestFetch:{[s;st;en;res] .achest.fetch4[s;st;en;res]}]
