/ qserver_proxy.q — q IPC proxy for FastAPI + LRU cache
fmtDate:{ssr[string x;".";"-"]};

/ LRU cache: query key → (table; timestamp)
.cache:()!();

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
  
  / Build cache key from query params (skip command name)
  qkey:`$"," sv string 1_ x;
  
  / Check cache — return if < 30 min old
  if[99h=type .cache;
    if[qkey in key .cache;
      c:.cache qkey;
      if[-12h=type c 0;
        if[.z.p < c 1 + 1800000000000; :c 0]]]];
  
  token:getenv`DATA_API_TOKEN;
  payload:.j.j `symbols`start`end`resolution`provider`format!(syms;st;en;res;prov;`q);
  
  fn:"/tmp/_qproxy_",string .z.i;
  (`$":",fn) 0: enlist payload;
  
  auth:$[""~token; ""; " -H 'Authorization: Bearer ",token,"'"];
  rfn:"/tmp/_qproxyresp_",string .z.i;
  curlcmd:"curl -s --max-time 30 --compressed",auth," -H 'Content-Type: application/json' -X POST -d @",fn," 'http://localhost:8001/v1/data' > ",rfn," 2>&1 || true";
  @[system;curlcmd;0N];
  @[system;"rm -f ",fn;0N];
  r:@[read0; `$":",rfn; 0N];
  @[system;"rm -f ",rfn;0N];
  if[0N~r; :`nocur];
  resStr:$[0h=type r; 10h$raze r,"\n"; string r];
  response:@[value; resStr; { @[.j.k; resStr; {`nodata}] }];
  
  / Cache table results (max 100 entries)
  if[98h=type response;
    .cache[qkey]:(response; .z.p);
    if[100<count key .cache;
      .cache:((count[key .cache] - 100) _ key .cache)#.cache];
    :response];
  
  `nodata
 };