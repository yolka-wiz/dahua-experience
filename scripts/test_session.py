#!/usr/bin/env python3
"""Test if the user-provided WebClientSessionID is still valid via /RPC2."""
import json
from curl_cffi import requests

BASE = "http://192.168.40.100"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:153.0) Gecko/20100101 Firefox/153.0"
HEADERS = {"User-Agent": UA, "Accept": "*/*", "Referer": BASE + "/"}

s = requests.Session(impersonate="firefox")
sid = "c58110a541b41fce7fb245a9d068369b"

# The app sends session in the JSON body (jsCore.RPC._data includes session)
for method, params in [
    ("global.getCurrentTime", None),
    ("userManager.getAuthorityList", {}),
    ("global.keepAlive", {"timeout": 300, "active": True}),
]:
    payload = {"method": method, "params": params, "id": 1, "session": sid}
    r = s.post(BASE + "/RPC2", data=json.dumps(payload), headers=HEADERS, timeout=15)
    print(f"[{method}] HTTP {r.status_code} -> {r.text[:300]}")
