/ qserver_proxy.q — q IPC proxy for FastAPI
fmtDate:{ssr[string x;".";"-"]};

/ Keep a small hot-result cache at the q boundary. Cache the typed table,
/ not the HTTP/q-text response, so warm IPC calls bypass curl and parsing.
CACHE_TTL:0D00:00:30;
CACHE_MAX:32;
CACHE:()!();
CACHE_TS:()!();
CACHE_KEYS:();

makeCacheKey:{[syms;st;en;res;prov]
  .j.j (syms;st;en;res;prov)
  };

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
  cacheId:makeCacheKey[syms;st;en;res;prov];
  if[cacheId in CACHE;
    if[.z.p-CACHE_TS cacheId<CACHE_TTL; :CACHE cacheId]
    ];
  
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
  / Try 1: value as q literal (format = "q" response)
  response:@[value; resStr; { 
    / Try 2: .j.k as JSON (error responses from FastAPI)
    @[.j.k; resStr; {`nodata}]
   }];
  / Cache only successful typed tables. Expired entries are overwritten.
  if[98h=type response;
    if[not cacheId in CACHE; CACHE_KEYS,:enlist cacheId];
    CACHE[cacheId]:response;
    CACHE_TS[cacheId]:.z.p;
    if[CACHE_MAX<count CACHE_KEYS;
      old:first CACHE_KEYS;
      CACHE_KEYS::1_ CACHE_KEYS;
      CACHE::CACHE except old;
      CACHE_TS::CACHE_TS except old
      ]
    ];
  / Return table if we got one, otherwise nodata
  response
 };