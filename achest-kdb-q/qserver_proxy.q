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
  curlcmd:"curl -s --max-time 30 --compressed",auth," -H 'Content-Type: application/json' -X POST -d @",fn," 'http://localhost:8001/v1/data'";
  
  / Run curl and capture output safely
  r:@[system;curlcmd;0N];
  @[system;"rm -f ",fn;0N];
  
  if[0N~r; :`nocur];
  
  / system returns a list of strings for multi-line output; flatten with newline or raze
  /resStr:$[0h=type r; 10h$raze r,"\n"; string r];
  
  /rfn:"/tmp/_qresp_",string .z.i;
  /(`$":",rfn) 0: enlist resStr;
  /:rfn;

/ parse JSON response and show the data or error
  resStr:$[0h=type r; 10h$raze r,"\n"; string r];
  
  / Safely parse JSON string into q dictionary
  response: @[.j.k; resStr; { -2 "JSON parse error: ", x; (`error)!enlist x }];
  
  / Check if it's an error dictionary or missing data
  if[99h ~ type response;
    if[`error in key response; :response];
    if[not `data in key response; :`nodata];
    :response`data
  ];
  
  :response