/ qserver_proxy.q — q IPC proxy for FastAPI
fmtDate:{ssr[string x;".";"-"]};
.z.pg:{
  cmd:first x;
  if[not `fetch~cmd; '`unknown];
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
  cmd:"curl -s --max-time 30 --compressed",auth," -H 'Content-Type: application/json' -X POST -d @",fn," 'http://localhost:8001/v1/data' 2>&1 || true";
  r:@[system;cmd;0N];
  @[system;"rm -f ",fn;0N];
  if[0N~r; '`nocur];
  if[0h=type r; r:raze r];
  if["curl: ("~9#r; '`curlerr];
  rfn:"/tmp/_qresp_",string .z.i;
  (`$":",rfn) 0: enlist r;
  rfn                                      / return filename
 };

