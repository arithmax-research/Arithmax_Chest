/ achest.q — native kdb+/q client for the Arithmax Chest API
/ ───────────────────────────────────────────────────────
/ Usage:
/   \l achest.q
/   .achest.get[`BTCUSDT; 2026.09.01; 2026.09.23; `minute]
/   .achest.get[`BTCUSDT; 2026.09.01; 2026.09.23; `minute; (`provider`token)!(`massive;`abc123)]
/   .achest.providers[]              / list providers
/   .achest.route[`AAPL;`daily;`auto] / route symbol
/   achestGet[`BTCUSDT; 2026.09.01; 2026.09.23; `minute]  / root alias

/ Check curl is available
if[0N~@[system;"which curl 2>/dev/null";0N];
  -2 "ERROR: achest.q requires curl on PATH";
  exit 1]

\d .achest

BASE_URL:"https://achestv2.misango.me"
TOKEN:first over getenv`DATA_API_TOKEN

/ ── Build JSON payload via .j.j ──────────────────────
mkpayload:{[syms;st;en;res;prov]
  syms:$[10h=type syms;enlist syms;syms];
  .j.j `symbols`start`end`resolution`provider`format!
        (syms;string[st];string[en];string[res];prov;`q)
 }

/ ── curl POST ────────────────────────────────────────
curlpost:{[payload;token]
  auth:$[null token; ""; " -H 'Authorization: Bearer ",token,"'"];
  cmd:"curl -s --max-time 120",
      auth,
      " -H 'Content-Type: application/json'",
      " -X POST -d '",payload,"' '",BASE_URL,"/v1/data'";
  r:@[system;cmd;{'"achest: curl failed: ",x}];
  if[11h=type r; r:first r];
  if[r~"{\"detail\":\"invalid client token\"}";
    '"achest: invalid/missing API token. Set DATA_API_TOKEN or pass `token"];
  r
 }

/ ── Public: fetch market data ────────────────────────
get:{[syms;st;en;res;opts]
  opts:enlist[`provider]!enlist`;
  if[0<count key opts; opts,:opts];
  prov:$[`provider in key opts; opts`provider; `auto];
  token:$[`token in key opts; opts`token; TOKEN];
  raw:curlpost[mkpayload[syms;st;en;res;prov];token];
  @[value;raw;{'"achest: parse failed: ",x,"\nraw:\n",y}[;raw]]
 }

/ ── 4-arg shorthand ─────────────────────────────────
get4:{[syms;st;en;res] .achest.get[syms;st;en;res;()!()] }

/ ── List providers ───────────────────────────────────
providers:{[]
  auth:$[null TOKEN; ""; " -H 'Authorization: Bearer ",TOKEN,"'"];
  raw:@[system;
    "curl -s",auth," '",BASE_URL,"/v1/providers'";
    {'"achest: curl failed: ",x}];
  @[value;raw;{'"achest: parse failed: ",x}] }

/ ── Route symbol ─────────────────────────────────────
route:{[sym;res;prov]
  auth:$[null TOKEN; ""; " -H 'Authorization: Bearer ",TOKEN,"'"];
  raw:@[system;
    "curl -s",auth," '",BASE_URL,"/v1/route?symbol=",string[sym],"&resolution=",string[res],"&provider=",string[prov],"'";
    {'"achest: curl failed: ",x}];
  @[value;raw;{'"achest: parse failed: ",x}] }

\d .

/ ── Root-level alias for easier VS Code use ──────────
if[not `achestGet in key `.;
  achestGet:{[s;st;en;res] .achest.get4[s;st;en;res]}]

/ ── Banner ───────────────────────────────────────────
-1 "┌─────────────────────────────────────────────────────────┐";
-1 "│ achest.q loaded — native kdb+/q market data client      │";
-1 "│                                                         │";
-1 "│  .achest.get[`BTCUSDT; 2026.09.01; 2026.09.23; `minute] │";
-1 "│  .achest.providers[]   .achest.route[`AAPL;`daily;`auto]│";
-1 "│  achestGet[`BTCUSDT; 2026.09.01; 2026.09.23; `minute]   │";
-1 "│                                                         │";
-1 "│  Set DATA_API_TOKEN env var or pass (`token;\"...\") in opts  │";
-1 "└─────────────────────────────────────────────────────────┘";