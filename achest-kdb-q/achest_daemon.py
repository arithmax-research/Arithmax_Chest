#!/usr/bin/env python3
"""
achest_daemon.py — Fastest keepalive daemon for achest.q

Clients:   q -> system(curl) -> daemon HTTP -> httpx pool -> FastAPI
IPC mode:  q -> hopen          -> daemon IPC -> httpx pool -> FastAPI

USAGE: python3 achest-kdb-q/achest_daemon.py [--port 9999]
       ACHEST_DAEMON_IPC=1 for experimental q IPC mode.
       ACHEST_DAEMON_BASE_URL env overrides backend endpoint.
"""
from __future__ import annotations
import argparse, json, os, socket, struct, sys, threading
import httpx

BASE_URL_ENV = "ACHEST_DAEMON_BASE_URL"
DEFAULT_BASE_URL = "http://46.225.46.174:8001"
_client = httpx.Client(timeout=httpx.Timeout(600, connect=10),
    limits=httpx.Limits(max_keepalive_connections=16, max_connections=32))
IPC_MODE = os.environ.get("ACHEST_DAEMON_IPC") == "1"

# ── HTTP handler (reliable) ────────────────────────────────────────

def handle_http(conn):
    try:
        buf = b""
        while True:
            c = conn.recv(1)
            if not c: raise ConnectionError("disconnected")
            buf += c
            if buf.endswith(b"\r\n\r\n"): break
        lines = buf.decode("utf-8",errors="replace").split("\r\n")
        ep = lines[0].split(" ",2)[1] if len(lines[0].split(" ",2))>1 else "/v1/data"
        cl, tk = 0, ""
        for l in lines[1:]:
            if ":" not in l: continue
            k,v = l.split(":",1)
            lk = k.strip().lower()
            if lk=="authorization": tk=v.strip().replace("Bearer ","",1)
            if lk=="content-length": cl=int(v.strip())
        body = b""
        while len(body)<cl:
            c = conn.recv(cl-len(body))
            if not c: break
            body += c
    except (ConnectionError,ValueError): conn.close(); return
    hdrs = {"Content-Type":"application/json","Accept-Encoding":"gzip"}
    if tk: hdrs["Authorization"]=f"Bearer {tk}"
    try:
        base = os.environ.get(BASE_URL_ENV,DEFAULT_BASE_URL).rstrip("/")
        r = _client.post(base+ep, data=body, headers=hdrs)
        conn.sendall(f"HTTP/1.1 {r.status_code} OK\r\nContent-Type:text/plain\r\n"
            f"Content-Length:{len(r.text)}\r\nConnection:close\r\n\r\n{r.text}".encode())
    except Exception as e:
        err = json.dumps({"error":str(e)})
        conn.sendall(f"HTTP/1.1 502 Bad Gateway\r\nContent-Type:application/json\r\n"
            f"Content-Length:{len(err)}\r\nConnection:close\r\n\r\n{err}".encode())
    finally: conn.close()

# ── q IPC handler (experimental) ───────────────────────────────────

def _rn(c,n):
    b=b""; 
    while len(b)<n:
        x=c.recv(n-len(b));
        if not x: raise ConnectionError(); b+=x
    return b

def _dq(endian, data, off):
    if off>=len(data): return None,off
    t = data[off]
    if t==1:  # symbol
        sl=struct.unpack(f"{endian}i",data[off+4:off+8])[0]
        if sl<0: return None,off+8
        return data[off+8:off+8+sl].decode("utf-8",errors="replace"),off+8+sl
    if t==10: # char list
        sl=struct.unpack(f"{endian}i",data[off+4:off+8])[0]
        if sl<0: return "",off+8
        return data[off+8:off+8+sl].decode("utf-8",errors="replace"),off+8+sl
    if t==0:  # mixed list
        cnt=struct.unpack(f"{endian}i",data[off+4:off+8])[0]; off+=8
        items=[]
        for _ in range(cnt):
            v,off=_dq(endian,data,off); items.append(v)
        return items,off
    return None,off+1

def handle_ipc(conn):
    try:
        e=_rn(conn,1)[0]; endian=">" if e else "<"
        _rn(conn,3)  # skip 3 unused bytes
        ml=struct.unpack(f"{endian}i",_rn(conn,4))[0]
        py=_rn(conn,ml-8) if ml>8 else b""
    except (ConnectionError,struct.error,OSError): conn.close(); return
    try:
        a,_=_dq(endian,py,0)
        if not isinstance(a,list) or len(a)<6: conn.close(); return
    except: conn.close(); return
    syms=str(a[1]) if a[1] else "BTCUSDT"
    st=str(a[2])[:10] if a[2] else "2026-10-01"
    en=str(a[3])[:10] if a[3] else "2026-10-06"
    res=str(a[4]) if a[4] else "daily"
    prov=str(a[5]) if a[5] else "auto"
    body=json.dumps({"symbols":[syms],"start":st,"end":en,
        "resolution":res,"provider":prov,"format":"q"})
    hdrs={"Content-Type":"application/json","Accept-Encoding":"gzip"}
    try:
        base=os.environ.get(BASE_URL_ENV,DEFAULT_BASE_URL).rstrip("/")
        r=_client.post(base+"/v1/data",data=body,headers=hdrs)
        rb=r.text.encode("utf-8")
        py=struct.pack(f"{endian}bi",10,len(rb))+rb
        msg=struct.pack(f"{endian}i",0)+struct.pack(f"{endian}i",len(py)+8)+py
        conn.sendall(msg)
    except Exception as e:
        err=f"daemon error: {e}".encode("utf-8")
        py=struct.pack(f"{endian}bi",10,len(err))+err
        msg=struct.pack(f"{endian}i",0)+struct.pack(f"{endian}i",len(py)+8)+py
        conn.sendall(msg)
    finally: conn.close()

# ── Server ─────────────────────────────────────────────────────────

def run(port):
    srv=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    srv.bind(("",port)); srv.listen(64)
    mode="IPC" if IPC_MODE else "HTTP"
    base=os.environ.get(BASE_URL_ENV,DEFAULT_BASE_URL)
    print(f"achest-daemon: {mode} port {port} -> {base}",file=sys.stderr,flush=True)
    while True:
        conn,_=srv.accept()
        tgt=handle_ipc if IPC_MODE else handle_http
        threading.Thread(target=tgt,args=(conn,),daemon=True).start()

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--port",type=int,default=9999)
    run(p.parse_args().port)

if __name__=="__main__": main()