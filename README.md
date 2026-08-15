# dahua-experience

Reverse-engineering notes, verified API knowledge, and working tooling for a
Dahua H5 Web3.0 NVR (DHI-NVR5232-4KS2) and the Cisco floor-switch camera fabric
behind it.

Everything here was verified against live hardware. No credentials are included —
set them via env vars or pull from a vault.

## What's inside

- `skills/` — the Hermes agent skills built from this work:
  - `dahua-h5-rpc-login.md` — full RPC2 login flow, WebUI session extraction via CDP, camera inventory structures, response-shape gotchas
  - `network-device-automation.md` — Cisco telnet patterns, camera→port MAC correlation, port-description workflow
- `scripts/` — working toolkit (see below)
- `docs/rpc_api_map.md` — verified RPC2 method inventory with param shapes
- `docs/ssh_enable_guide.txt` — researched SSH-enablement notes for Dahua NVRs (with caveats)
- `data/cam_inventory.json` — 32-channel camera inventory (IP/MAC/SN/title)

## The NVR (192.168.40.100)

- Model: DHI-NVR5232-4KS2, FW 4.002.0000000.8.R (2024-10-30), SN 8B02C47PAZ58EDD, name "NVR-BORNA RAD"
- H5 Web3.0 UI: no classic CGI login, no telnet/SSH on this firmware. Access = JSON-RPC over `/RPC2_Login` + `/RPC2`, RTSP, and HTTP CGI only.
- Ports: 80 (web), 37777 (Dahua private/device protocol), 554 (RTSP), 5060 (SIP)
- 32 channels: 30 Connected, ch26 REAR_L Unconnect (physical fault), ch31 Empty spare
- All 31 registered cameras are Dahua IPCs on 192.168.40.x (IPC-HDW2431TM-AS-S2 domes, IPC-HFW2431S-S-S2 bullets, one IPC-HDW2531T at .225), Dahua Private protocol :37777, admin creds stored on NVR

## RPC2 login flow (verified)

1. Probe `POST /RPC2_Login` with `{"method":"global.login","params":{"userName":U,"password":"","clientType":"Web3.0","loginType":"Direct"},"id":1}` — response params carry `encryption` ("Default"), `realm`, `random`; body carries `session`.
2. Hash: `inner = md5(user + ":" + realm + ":" + password)`, `enc = md5(user + ":" + random + ":" + inner)` (lowercase hex).
3. Re-POST with `password=enc`, plus `"authorityType":encryption`, `"passwordType":encryption`, and top-level `"session"` from the probe.
4. Session rides in the JSON body (`"session": sid`) on every subsequent `/RPC2` call — NOT a cookie.
5. Keep alive: `{"method":"global.keepAlive","params":{"timeout":300,"active":true},"id":N,"session":sid}`.

Gotchas:
- **Response shape trap**: Dahua RPC2 returns `{"result": <bool>, "params": <payload>}` — `result` is a success flag, the actual data lives in `params`. Don't read `result` as the payload.
- Classic digest CGI login is dead on H5 firmware — don't waste lockout budget on it (failed logins decrement `remainLoginTimes`, lockout ~300s).
- Sessions can be browser-bound (cookie state) vs script-usable (pcap-extracted). If a fresh session from the browser is rejected from scripts, capture one from live traffic or via CDP with the browser's headers.

## Camera inventory structures (verified)

- `ChannelTitle.table` → plain list of `{Name}` objects; list index == channel number.
- `RemoteDevice.table` → dict keyed `uuid:System_CONFIG_NETCAMERA_INFO_N` (N = channel), each entry carries IP, MAC, SN, model, firmware, video input name.
- Status probe: `RemoteDevice.getCameraLoginErrorCode` — 268632100 = channel issue (camera offline), 268632084 = healthy channel baseline.
- Diagnostic pattern: Unconnect + errorCode 268632100 + ping fail = camera offline at the physical layer, not an NVR config problem.

## Switch fabric (VLAN 40)

- Switches: SW-F0 (192.168.1.100) .. SW-F5 (192.168.1.105), SW-CORE (192.168.1.110). Cisco, telnet, same account set on all.
- All cameras on VLAN 40. 30 direct camera ports mapped (correlated NVR MAC inventory ↔ switch MAC table) and labeled with `cam <NAME>` descriptions in running-config.
- Floor mapping: F0 + F-1 cams on SW-F0; F1 (incl. REAR_R Gi1/0/48) on SW-F1; F2/F3/F4/F5/ASANSOR (Gi1/0/20) on their switches; everything else rides trunks (Gi1/0/49 → core, LACP Po5).
- One computer on VLAN 40: Gigabyte device on SW-F0 Gi1/0/20 (1000M, no PoE draw).

### REAR_L diagnosis (ch26, 192.168.40.16)

- Not in any switch MAC table, NVR Unconnect, not pingable.
- SW-F1 Gi1/0/46: link UP, PoE 15.4W (camera-class draw), but learns NO MAC, 165K input errors + 71 CRC over 110GB historical traffic → camera physically present and powered but its data path is dead (bad cable pair / dead camera NIC). Gi1/0/47: notconnect, nothing plugged.
- Conclusion: physical fix at the camera/cable end, not a switch config problem.

## Scripts

| Script | Purpose |
|---|---|
| `cdp.py` | Extract live session straight from the VNC Chromium via CDP debug port (no pcap parsing) |
| `cam_status.py` | Full camera status sweep (30/32 channels, titles, IPs, states) |
| `rpc_login.py` | Full RPC2 login flow (env: NVR_USER/NVR_PASS) |
| `rpc_probe.py` | Read-only RPC method explorer |
| `rpc_session.py` / `test_session.py` | Validate a session token |
| `dahua_session.py` | Session helpers |
| `pcap_rpc.py` | Parse captured RPC traffic (handles Linux cooked SLL2 framing) |
| `switch_vlan40_sweep.py` | MAC-table sweep of all 6 floor switches + core, correlates cameras (env: SW_PASS) |
| `apply_port_descriptions.py` | Writes `cam <NAME>` descriptions to ports (env: SW_PASS) |

## Credits / references

- rroller/dahua — Home Assistant Dahua CGI client (camera-side API reference)
- Denis Kucevic — RPC reverse engineering (system.listService / service.listMethod probing)
- `docs/ssh_enable_guide.txt` — SSH enablement research with caveats (firmware-dependent, voids warranty, no official support on this model)
