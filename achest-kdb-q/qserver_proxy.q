/ qserver_proxy.q — q IPC proxy for the Arithmax Chest API
/ ──────────────────────────────────────────────────────────────
/ Deployment:
/   Place kc.lic in ~/.kx/ or QLIC directory
/   q qserver_proxy.q -p 5001 -QLIC /path/to/license/dir
/
/ Client usage:
/   h:hopen `:aws-host:5001
/   neg[h] (`fetch; `BTCUSDT; 2026.09.01; 2026.10.06; `second)
/   tbl: h[]
/   hclose h

/ ── Config ────────────────────────────────────────────────────
BASE_URL:"http://localhost:8000"           / local FastAPI (same container/host)
TOKEN:getenv`DATA_API_TOKEN               / proxied auth token (optional)

/ ── Request handler ───────────────────────────────────────────
.z.pg:{
  / Parse incoming IPC message — expects: (`fetch; sym; start; end; res; provider)
  cmd:first x;
  if[not `fetch~cmd; :'`unknown_command];

  syms:enlist $[10h=type x 1; x 1; string x 1];           / symbol (always a list)
  st:string  $[10h=type x 2; x 2; x 2];                   / start date
  en:string  $[10h=type x 3; x 3; x 3];                   / end date
  res:string $[10h=type x 4; x 4; x 4];                   / resolution
  prov:string $[10h=type x 5; "auto"; string x 5];         / provider

  / Build JSON payload
  payload:.j.j `symbols`start`end`resolution`provider`format!
              (syms; st; en; res; prov; `q);

  / Write payload to temp file and curl
  fn:"/tmp/_qproxy_",string .z.i;
  (`$":",fn) 0: enlist payload;
  auth:$[""~TOKEN; ""; " -H 'Authorization: Bearer ",TOKEN,"'"];
  cmd:"curl -s --max-time 600 --compressed",
      auth,
      " -H 'Content-Type: application/json'",
      " -X POST -d @",fn," '",BASE_URL,"/v1/data' 2>&1 || true";
  r:@[system;cmd;0N];
  @[system;"rm -f ",fn;0N];

  / Handle errors
  if[0N~r; :'`proxy_curl_failed];
  if[0h=type r; r:raze r];
  if["curl: ("~9#r; :'`proxy_curl_error, `error_msg$(r)];
  if[not 10h=type r; :'`proxy_unexpected_type];

  / Parse q literal and return native table
  @[value;r;{'\"proxy: parse failed: \",x,\"\nraw:\n\",y}[;r]]
 }

\

/ ── Example test (run locally) ───────────────────────────────
/ 1. Start both:
/    uvicorn achest.server:app --port 8000 &
/    q qserver_proxy.q -p 5001
/
/ 2. Connect from another q session:
/    h:hopen `:localhost:5001
/    neg[h] (`fetch; `BTCUSDT; 2026.09.01; 2026.10.06; `daily)
/    show h[]
/    hclose h