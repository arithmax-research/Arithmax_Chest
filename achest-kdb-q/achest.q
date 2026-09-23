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
TOKEN:getenv`DATA_API_TOKEN

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
/ ── curl POST ────────────────────────────────────────
curlpost:{[payload;token]
  auth:$[""~token; ""; " -H 'Authorization: Bearer ",token,"'"];
  cmd:"curl -s --max-time 120",
      auth,
      " -H 'Content-Type: application/json'",
      " -X POST -d '",payload,"' '",BASE_URL,"/v1/data'";
  r:@[system;cmd;{'"achest: curl failed: ",x}];
  if[0h=type r; r:raze r];           / join list of lines into one string
  if[10h=type r; :r];                / already a string — return as-is
  '"achest: unexpected curl response type: ",string[type r]
 }

/ ── Public: fetch market data ────────────────────────
fetch:{[syms;st;en;res;opts]
  o:$[99h=type opts; opts; (enlist`provider)!enlist` ];
  prov:$[`provider in key o; o`provider; `auto];
  token:$[`token in key o; o`token; TOKEN];
  raw:curlpost[mkpayload[syms;st;en;res;prov];token];
  @[value;raw;{'"achest: parse failed: ",x,"\nraw:\n",y}[;raw]]
 }

/ ── 4-arg shorthand ─────────────────────────────────
fetch4:{[syms;st;en;res] .achest.fetch[syms;st;en;res;()!()] }

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
