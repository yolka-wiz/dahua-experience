#!/usr/bin/env python3
"""Full Dahua H5 Web3.0 login over /RPC2_Login, replicating the app's flow."""
import base64, hashlib, json, os
from curl_cffi import requests

BASE = "http://192.168.40.100"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:153.0) Gecko/20100101 Firefox/153.0"
HEADERS = {
    "User-Agent": UA,
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": BASE + "/",
}

def md5(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()

def rpc_post(session, path, payload, ctype=None):
    h = dict(HEADERS)
    if ctype:
        h["Content-Type"] = ctype
    r = session.post(BASE + path, data=json.dumps(payload), headers=h, timeout=15)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, r.text

def login(user, pw, ctype="application/json"):
    s = requests.Session(impersonate="firefox")
    reqid = [1]

    def send(path, method, params, extra=None):
        body = {"method": method, "params": params, "id": reqid[0]}
        reqid[0] += 1
        if extra:
            body.update(extra)
        st, resp = rpc_post(s, path, body, ctype)
        return st, resp

    # 1) probe: empty password (app sends loginType too)
    st, resp = send("/RPC2_Login", "global.login",
                    {"userName": user, "password": "", "clientType": "Web3.0",
                     "loginType": "Direct"})
    print(f"[probe] HTTP {st} -> {json.dumps(resp)[:300] if not isinstance(resp, str) else resp[:300]}")
    if st != 200 or not isinstance(resp, dict):
        return None
    session = resp.get("session")
    params = resp.get("params") or {}
    encryption = params.get("encryption", "Default")
    realm = params.get("realm", "")
    random = params.get("random", "")
    print(f"  session={session} encryption={encryption} realm={realm} random={random}")

    # 2) compute password exactly like getAuth(c, t):
    #    getAuth passes NO clientType -> webEncryption r is undefined -> double md5 with random
    if encryption == "Basic":
        enc_pw = base64.b64encode(f"{user}:{pw}".encode()).decode()
        print("  password scheme: Basic base64")
    elif encryption == "Default":
        o = md5(f"{user}:{realm}:{pw}")
        enc_pw = md5(f"{user}:{random}:{o}")
        print("  password scheme: Default md5(user:random:md5(user:realm:pass))")
    else:
        enc_pw = pw
        print(f"  password scheme: unknown ({encryption}), sending plain")

    # 3) real login
    st, resp = send("/RPC2_Login", "global.login",
                    {"userName": user, "password": enc_pw, "clientType": "Web3.0",
                     "loginType": "Direct",
                     "authorityType": encryption, "passwordType": encryption},
                    extra={"session": session})
    print(f"[login] HTTP {st} -> {json.dumps(resp)[:300] if not isinstance(resp, str) else resp[:300]}")
    if st != 200 or not (isinstance(resp, dict) and resp.get("result")):
        return None
    session = resp.get("session") or session
    print(f"[login] SUCCESS session={session}")

    # 4) verify with an authed RPC call
    for method in ["userManager.getAuthorityList", "global.keepAlive"]:
        try:
            st, resp = send("/RPC2", method, {} if method == "userManager.getAuthorityList" else {"timeout": 300, "active": True})
            print(f"[verify {method}] HTTP {st} -> {json.dumps(resp)[:250] if not isinstance(resp, str) else resp[:250]}")
        except Exception as e:
            print(f"[verify {method}] ERR {e}")
    return session

if __name__ == "__main__":
    print("=== a.alavi ===")
    s1 = login(os.environ.get("NVR_USER", "a.alavi"), os.environ.get("NVR_PASS", ""))
