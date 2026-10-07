/ qserver_proxy.q — q IPC proxy for FastAPI
fmtDate:{ssr[string x;".";"-"]};

.z.pg:{[x]
  cmd:first x;
  if[not `text~cmd; if[not `fetch~cmd; '`unknown]];

  / Handle remote file read & cleanup request
  if[`read~cmd;
    rfn: x 1;
    res: read0 `$rfn;
    system "rm -f ",rfn;
    :res];

  / ... existing fetch / text logic ...
  
  syms:enlist $[10h=type x 1; x 1; string x 1];
  st:fmtDate x 2;
  en:fmtDate x 3;
  res:$[10h=type x 4; x 4; string x 4];
  prov:$[10h=type x 5; x 5; "auto"];
  token:getenv`DATA_API_TOKEN;
  payload:.j.j `symbols`start`end`resolution`provider`format!(syms;st;en;res;prov;`q);
  
  fn:"/tmp/_qproxy_",string .z.i;
  (`$":",fn) 0: enlist payload;
  
  auth:$[""~token; ""; " -H 'Authorization: Bearer ",token,"'"];
  rfn:"/tmp/_qproxyresp_",string .z.i;
  curlcmd:"curl -s --max-time 600 --compressed",auth," -H 'Content-Type: application/json' -X POST -d @",fn," 'http://localhost:8001/v1/data' > ",rfn," 2>&1 || true";
  @[system;curlcmd;0N];
  @[system;"rm -f ",fn;0N];
  r:@[read0; `$":",rfn; 0N];
  @[system;"rm -f ",rfn;0N];
  if[0N~r; '"qproxy: failed to read curl response"];
  if[0=count r; '"qproxy: empty response from FastAPI"];
  resStr:$[0h=type r; 10h$raze r,"\n"; string r];
  if["curl: ("~9#resStr; '"qproxy: ",resStr];
  / Try 1: value as q literal (format = "q" response)
  response:@[value; resStr; { 
    / Try 2: .j.k as JSON (error responses from FastAPI)
    @[.j.k; resStr; {`nodata}]
   }];
  / Return table if we got one, otherwise nodata
  response
 };