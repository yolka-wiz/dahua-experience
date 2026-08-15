#!/usr/bin/env python3
"""Camera status sweep for Dahua NVR via live RPC session pulled from Chromium CDP.
Read-only: camera state, titles, remote devices. No settings are modified.
Usage: ./venv/bin/python cam_status.py [--json]
"""
import argparse, json, sys
from curl_cffi import requests
from cdp import cdp  # sibling helper: cdp("Network.getAllCookies")

NVR = "http://192.168.40.100"
S = requests.Session(impersonate="firefox", timeout=10)

def get_session():
    cookies = cdp("Network.getAllCookies").get("cookies", [])
    for c in cookies:
        if c["name"] == "WebClientSessionID":
            return c["value"]
    raise RuntimeError("WebClientSessionID cookie not found in browser")

def rpc(method, params=None, session=None, sid=None):
    body = {"method": method, "params": params or {}, "id": 1}
    if session:
        body["session"] = session
    r = S.post(f"{NVR}/RPC2", json=body, timeout=10)
    j = r.json()
    if j.get("error"):
        return {"_error": j["error"], "_method": method}
    # Dahua RPC2: "result" is a bool success flag, payload lives in "params"
    return j.get("params", j.get("result", {}))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    sid = get_session()
    # verify session
    auth = rpc("userManager.getAuthorityList", {}, session=sid)
    if isinstance(auth, dict) and "_error" in auth:
        print("SESSION DEAD:", auth["_error"])
        sys.exit(1)

    state = rpc("LogicDeviceManager.getCameraState", {"uniqueChannels": [-1]}, session=sid)
    titles = rpc("configManager.getConfig", {"name": "ChannelTitle", "onlyLocal": False}, session=sid)
    remotes = rpc("configManager.getConfig", {"name": "RemoteDevice", "onlyLocal": False}, session=sid)

    # normalize titles: ChannelTitle.table is a LIST, index == channel
    title_map = {}
    tbl = titles.get("table", titles)
    if isinstance(tbl, list):
        for i, item in enumerate(tbl):
            if isinstance(item, dict):
                title_map[i] = item.get("Name", "")

    # remote devices: dict keyed "uuid:System_CONFIG_NETCAMERA_INFO_N", N == channel
    dev_map = {}
    rt = remotes.get("table", remotes)
    if isinstance(rt, dict):
        for k, d in rt.items():
            if not isinstance(d, dict):
                continue
            try:
                ch = int(k.rsplit("_", 1)[-1])
            except (TypeError, ValueError):
                continue
            vin = (d.get("VideoInputs") or [{}])[0] if isinstance(d.get("VideoInputs"), list) else {}
            dev_map[ch] = {
                "ip": d.get("Address", ""),
                "sn": d.get("SerialNo", d.get("Name", "")),
                "vendor": d.get("Vendor", ""),
                "proto": d.get("ProtocolType", ""),
                "user": d.get("UserName", ""),
                "enable": d.get("Enable", ""),
                "model": d.get("DeviceType", ""),
                "fw": d.get("Version", ""),
                "mac": d.get("Mac", ""),
                "input_name": vin.get("Name", ""),
            }

    rows = []
    for e in state.get("channelStates", state.get("states", state.get("channels", []))):
        if not isinstance(e, dict):
            continue
        ch = e.get("channel", e.get("Channel"))
        if ch is None:
            continue
        st = e.get("connectionState", e.get("state", "?"))
        dev = dev_map.get(ch, {})
        rows.append({
            "channel": ch,
            "state": st,
            "title": title_map.get(ch, "") or dev.get("input_name", ""),
            "ip": dev.get("ip", ""),
            "sn": dev.get("sn", ""),
            "vendor": dev.get("vendor", ""),
            "proto": dev.get("proto", ""),
            "user": dev.get("user", ""),
            "enable": dev.get("enable", ""),
            "model": dev.get("model", ""),
            "fw": dev.get("fw", ""),
            "mac": dev.get("mac", ""),
        })

    rows.sort(key=lambda r: (r["channel"] if isinstance(r["channel"], int) else 999))
    if args.json:
        print(json.dumps(rows, indent=2))
        return

    # summary
    from collections import Counter
    cnt = Counter(r["state"] for r in rows)
    print(f"Session {sid[:8]}… valid. Channels: {len(rows)} | " +
          ", ".join(f"{k}={v}" for k, v in sorted(cnt.items())))
    print("-" * 130)
    print(f"{'CH':>3} {'STATE':<11} {'TITLE':<24} {'IP':<16} {'MODEL':<22} {'FW':<24} {'MAC':<18} {'PROTO':<8} {'EN':<5}")
    for r in rows:
        print(f"{r['channel']:>3} {r['state']:<11} {r['title'][:23]:<24} "
              f"{r['ip']:<16} {r['model'][:21]:<22} {r['fw'][:23]:<24} "
              f"{r['mac']:<18} {r['proto']:<8} {str(r['enable']):<5}")

if __name__ == "__main__":
    main()
