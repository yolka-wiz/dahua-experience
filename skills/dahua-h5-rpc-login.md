---
name: dahua-h5-rpc-login
description: Use when logging into Dahua H5 Web3.0 NVRs/DVRs via RPC.
---

# Dahua H5 Web3.0 RPC Login (curl_cffi)

Modern Dahua NVRs (DHI-NVR5232-4KS2 and similar, firmware with H5 / "Web3.0" web UI) do NOT use the classic /cgi-bin login. The browser talks to /RPC2_Login with JSON-RPC-ish bodies. SSH is usually closed; access is HTTP + cookies (WebClientSessionID) or the RPC session.

## Prereqs

- Python 3 with curl_cffi: `pip install curl_cffi` (on Debian system pip: `pip install --break-system-packages curl_cffi`). Needed for TLS fingerprint impersonation: `requests.Session(impersonate="firefox")`.
- Working scripts: /home/agent/nvr/rpc_login.py (full login), /home/agent/nvr/test_session.py (validate a browser-provided WebClientSessionID), /home/agent/nvr/cdp.py (pull session + cookies from the VNC browser over CDP — preferred), /home/agent/nvr/cam_status.py (full camera status sweep).

## Fingerprint / recon

- Port 37777 open = Dahua proprietary binary protocol. Also typical: 80 (H5 web), 554 (RTSP), 5060 (SIP), 2000 (SDK), 8088 (SDK/config).
- HTTP root returns ExtJS "WEB SERVICE" page; JS bundles under /baseProj/js/... and /app/plugin/... Loadable with plain curl + Firefox UA + Referer http://<ip>/ + Cookie `curLanguage=English; WebClientSessionID=...; username=a.alavi`.
- Device identity from `http://<ip>/config/deviceInfo` or the JS config dump (deviceType DHI-NVR5232-4KS2 etc.).
- No root shell, no telnet on modern firmware. Text access = RPC + RTSP + HTTP CGI only.

## Login flow (verified against DHI-NVR5232-4KS2, Web3.0)

1) Probe: POST /RPC2_Login, body {"method":"global.login","params":{"userName":U,"password":"","clientType":"Web3.0","loginType":"Direct"},"id":1}
   Response params carry: encryption ("Default"), realm, random; body carries session.

2) Compute password hash exactly like the app's getAuth(user, password):
   - "Default" (realm+random double md5, this is what the H5 app actually sends — note getAuth is called WITHOUT clientType, so the random variant applies):
       inner = md5(user + ":" + realm + ":" + password)
       enc   = md5(user + ":" + random + ":" + inner)
   - "Basic": base64(user:password).
   - md5 = lowercase hex (faultylabs.MD5 lib; standard).

3) Real login: POST /RPC2_Login with same params but password=enc, plus "authorityType":encryption, "passwordType":encryption, and top-level "session":<from probe>.

4) Session = resp["session"]. Use it by adding top-level "session": sid to every /RPC2 POST body (NOT a cookie — the RPC layer carries it in JSON).

5) Verify: POST /RPC2 {"method":"userManager.getAuthorityList","params":{},"id":1,"session":sid} — 200 + result = live. Keep sessions alive with {"method":"global.keepAlive","params":{"timeout":300,"active":true},"id":N,"session":sid}.

## Pitfalls

- Classic digest CGI login (/cgi-bin/userLogin.cgi or login.cgi with Digest) fails with 400/401 on H5 firmware — the old libcurl Digest flow is dead there. Don't waste attempts; reverse the JS instead.
- Login lockout: failed logins decrement "remainLoginTimes" (shown in the failed response, ~7-9 left); hitting 0 locks the account ~300s. Stop after 2-3 credential attempts and verify creds before more tries.
- The WebClientSessionID cookie from a browser session goes stale — test it with test_session.py (RPC with session in body); "Invalid session in request data" = expired.
- Vault creds (vault-get CAM) can be stale even when the account is right; confirm with the user before repeated attempts.
- Static JS bundles are served with If-Modified-Since/ETag — fine to just GET them; grep the JS for "global.login", "RPC2_Login", "webEncryption", "getAuth" to re-derive the flow on other firmware versions.
curl_cffi Session(impersonate="firefox") avoids "tls fingerprint rejected" failures; the user's browser UA string works too.
Python venv for scraping tools: /home/agent/nvr/venv (curl_cffi + scrapling) — never pip install into system Python (Debian trixie is externally-managed).
VNC browser workaround (session is IP-bound, so run the browser ON the agent box): Xvfb :1 + x11vnc :5901 (rfbauth /home/agent/vnc/vncpass, letters-only pw) + noVNC over HTTPS on :6080 (self-signed /home/agent/vnc/novnc.{crt,key}, SANs include both agent IPs) + Chromium --remote-debugging-port=9222 --remote-allow-origins=* with DISPLAY=:1 and --user-data-dir=/home/agent/vnc/chrome-profile. Tab list: curl http://127.0.0.1:9222/json. NOTE: closing the last Chromium tab exits the browser — open a new tab with /json/new?URL first, or restart Chromium. Restart daemons with terminal(background=true) — Hermes blocks setsid/nohup wrappers; and pkill -f patterns can self-match and kill the shell (use explicit PIDs).

## WebUI session extraction via CDP (preferred over pcap)

Once the user logs into the NVR in the VNC Chromium, pull the live session directly — no password hashing, no pcap parsing:

    /home/agent/nvr/venv/bin/python /home/agent/nvr/cdp.py cookies
    # -> WebClientSessionID = <hex> (also curLanguage, username)

cdp.py talks DevTools WebSocket to ws://127.0.0.1:9222 (needs --remote-allow-origins=* or external WS origins are blocked). Then use the session in RPC bodies. This session is bound to the box's IP and kept alive by the browser's own keepAlive — it stays valid as long as the browser tab stays logged in. Re-run cdp.py after any browser restart; don't hardcode stale tokens.

CRITICAL response shape (this bites everyone): Dahua RPC2 responses are {"result": <bool>, "params": <payload>, "error": ...} — "result" is a SUCCESS FLAG, the actual data lives in "params". Always return j.get("params") from your RPC helper, NOT j.get("result") (that gives True/False).

## RTSP (also text)

RTSP on 554 answers OPTIONS/DESCRIBE with 401 + Digest challenge — usable with NVR credentials. Dahua stream path: /cam/realmonitor?channel=N&subtype=0 (main) or 1 (sub).

## RPC API map (read-only recon, verified 2026-08 on FW 4.002.0000000.8.R)

Full method inventory + param shapes live in /home/agent/nvr/rpc_api_map.md. Scripts: rpc_probe.py (surface sweep), rpc_channels.py (camera states/titles), rpc_network.py (network + remote camera inventory), pcap_rpc.py (parse a tcpdump pcap of the UI's own RPC calls to learn exact call shapes — datalink on this box is SLL2/276, not Ethernet, so dpkt needs the sll2 branch).

Key facts:
- magicBox.* gives identity: getProductDefinition {"name":feature}, getDeviceType, getSoftwareVersion, getSerialNo, getMachineName, getSystemInfo, getVendor, getDeviceClass. Many other magicBox getters do NOT exist on this FW (error 268894210 "Method not found!").
- configManager.getConfig {"name":Table,"onlyLocal":false} — OK for: Network, General, Record, RecordMode, Alarm, ChannelTitle, RemoteDevice (full camera inventory uuid:System_CONFIG_NETCAMERA_INFO_N with IP/MAC/SN/creds), RemoteDeviceLimitList, Stream, Email, AutoMaintain, DDNS, PPPoE, NAT, Multicast, Time, Holiday, MotionDetect, MediaEncrypt, AlarmOut, etc.
- Account-dependent DENIAL: 285278249 "Authority:check failure." — the a.alavi account CANNOT read VideoEncode/Snapshot/Storage/PTZ/VideoAnalyze/User/Security/FTP/HDDManage/Upgrade/IPFilter etc. An admin account could. Do not conclude a table doesn't exist from that error — check with admin first.
- Channel state: LogicDeviceManager.getCameraState {"uniqueChannels":[-1]} -> 32x {channel, connectionState: Connected|Unconnect|Empty}. getCameraLoginErrorCode {"channel":N} (268632084 = healthy, 268632100 = channel/connection problem; verify with ping from agent box).
- Camera inventory (verified shapes, cam_status.py):
  - ChannelTitle.table is a LIST of {"Name":...}, index == channel number (0-based).
  - RemoteDevice.table is a DICT keyed "uuid:System_CONFIG_NETCAMERA_INFO_N" where N == channel. Each value has Address, Mac, SerialNo, DeviceType (model), Version (firmware), UserName, Enable, VideoInputs[0].Name (input title).
- Connection status check: if getCameraState says Unconnect, ping the camera IP from the agent box — offline camera (PoE/power/cable) vs NVR-side config issue.
- Playback search: mediaFileFind.factory.create -> findFile {"condition":{"Channel":N,"StartTime":"...","EndTime":"...","Types":["dav"],"VideoStream":"Main","Events":["*"]}} -> findNextFile {"count":1024} -> close/destroy.
- ptz.factory.instance {"channel":N} + ptz.getCurrentProtocolCaps (instance context required; standalone errors -267976703). deviceDiscovery.factory.instance/attach/start/stop = LAN scan.
- userManager.getAuthorityList works; getUserList/getAllUsers don't exist on this FW.
- CAUTION: the web UI itself fires configManager.setConfig (e.g. SyncLocalityConfig, AutoAddRemoteDevice) on page load while you watch — seeing setConfig in a capture is NOT proof the operator changed settings.
