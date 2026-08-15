#!/usr/bin/env python3
"""Read-only RPC surface probe for Dahua H5 NVR.
Uses an existing live session (no login). Never calls setConfig / reboot / delete.
Prints per-method: OK with summary, or ERROR with code/message."""
import json, sys, time
from curl_cffi import requests

NVR = "http://192.168.40.100"
SID = sys.argv[1] if len(sys.argv) > 1 else "d9af78750635cc07c2003762aef950a3"
_id = 0

s = requests.Session(impersonate="firefox")

def rpc(method, params=None, timeout=10):
    global _id
    _id += 1
    body = {"method": method, "params": params if params is not None else {}, "id": _id, "session": SID}
    try:
        r = s.post(NVR + "/RPC2", json=body, timeout=timeout)
        obj = r.json()
    except Exception as e:
        return ("HTTPERR", str(e))
    if "error" in obj:
        return ("ERROR", obj["error"])
    return ("OK", obj.get("result"), obj.get("params"))

def show(label, method, params=None):
    res = rpc(method, params)
    if res[0] == "OK":
        _, result, params = res
        # summarize: truncate long blobs but keep structure
        def summ(x, depth=0):
            if depth > 3:
                return type(x).__name__
            if isinstance(x, dict):
                keys = list(x.keys())
                if len(keys) > 8:
                    keys = keys[:8] + [f"...(+{len(x)-8})"]
                return {k: summ(v, depth+1) for k, v in x.items() if k in keys} if False else {k: summ(x[k], depth+1) for k in keys if k in x}
            if isinstance(x, list):
                if len(x) > 5:
                    return [summ(x[0], depth+1), f"...(+{len(x)-1})"] if x else []
                return [summ(i, depth+1) for i in x]
            if isinstance(x, str) and len(x) > 80:
                return x[:80] + "..."
            return x
        print(f"OK   {method} -> {json.dumps(summ(params), ensure_ascii=False)[:400]}")
    elif res[0] == "ERROR":
        print(f"ERR  {method} -> {json.dumps(res[1], ensure_ascii=False)[:160]}")
    else:
        print(f"HTTP {method} -> {res[1][:120]}")

print(f"=== Session {SID[:8]}... ===")
show("keepalive", "global.keepAlive", {"timeout": 300, "active": True})

print("\n--- magicBox info ---")
for m in ["getProductDefinition", "getDeviceType", "getHardwareVersion", "getSoftwareVersion",
          "getSerialNo", "getMAC", "getMachineName", "getSystemInfo", "getVendor",
          "getDeviceModel", "getDeviceClass", "getDeviceFamily", "getLanguage",
          "getCurrentTime", "getLocalTime", "getTimeZone", "getLoginType",
          "getRemoteDeviceNumber", "getLocalZone"]:
    show("magicBox", "magicBox." + m)
for feat in ["VideoAnalyse", "RemoteVideoAnalyse", "HasTalk", "HasAlarm", "HasAudio",
             "HasPtz", "IsCVR", "HasBackup", "HasVto"]:
    show("magicBox", "magicBox.getProductDefinition", {"name": feat})

print("\n--- configManager.getConfig (known + guessed tables) ---")
for name in ["Network", "NetWork", "General", "VideoEncode", "Record", "RecordMode",
             "Snapshot", "Storage", "Alarm", "PTZ", "ChannelTitle", "Camera",
             "VideoAnalyze", "RemoteDevice", "Stream", "Encode", "Audio", "Display",
             "DateTime", "Account", "User", "Security", "SSL", "Email", "FTP",
             "SMTP", "NFS", "ISCSI", "RAIDs", "HDDManage", "Disk", "Backup",
             "AutoMaintain", "Upgrade", "CloudUpgrade", "DDNS", "Wifi", "Wlan",
             "PPPoE", "IPFilter", "Port", "NAT", "UPnP", "Multicast", "Qos",
             "Route", "GbE", "Locales", "VirtualHostProxy", "SyncLocalityConfig",
             "AutoAddRemoteDevice", "RemoteDeviceLimitList", "AlarmOut", "MediaEncrypt",
             "Time", "DaylightSaving", "Holiday", "MotionDetect", "FaceDetect",
             "ANR", "SnapshotMode", "VideoOutput", "TV", "Talk", "Phone",
             "NetworkDetection", "NetWorkDetection", "RemoteDeviceCaps", "SATAPlan"]:
    show("cfg", "configManager.getConfig", {"name": name, "onlyLocal": False})

print("\n--- userManager ---")
for m in ["getAuthorityList", "getUserList", "getAllUsers", "getUserInfo", "getCaps"]:
    show("user", "userManager." + m)

print("\n--- system ---")
for m in ["getCurrentTime", "getTimeZone", "getLanguage", "getVersion", "getSystemInfo",
          "getDeviceType", "getSerialNo"]:
    show("sys", "system." + m)

print("\n--- storage / disk ---")
for m in ["getDiskInfo", "getGroupInfo", "getHDDInfo", "getStorageInfo", "getRAIDInfo",
          "getVolumeInfo"]:
    show("stor", "storageManager." + m)

print("\n--- camera / channel ---")
show("cam", "LogicDeviceManager.getVideoChannelsInfo", {"type": "Input"})
show("cam", "LogicDeviceManager.getVideoChannelsInfo")
show("cam", "LogicDeviceManager.getCameraState", {"uniqueChannels": [-1]})
show("cam", "VideoLink.getAllLinkChannels")
show("cam", "POS.getAll")

print("\n--- ptz (read caps, then destroy) ---")
show("ptz", "ptz.factory.instance", {"channel": 0})
show("ptz", "ptz.getCurrentProtocolCaps")
show("ptz", "ptz.factory.destroy", {"channel": 0})

print("\n--- misc read-only ---")
show("misc", "CloudUpgrader.getAutoCheck")
show("misc", "RemoteDeviceManager.factory.instance")
show("misc", "RemoteDeviceManager.getCaps")
show("misc", "pwdAgent.getPreSecret")
show("misc", "workDirectory.factory.instance", {"name": "/"})
show("misc", "workDirectory.getBitmapEx", {"condition": {"Channel": -1, "Events": ["*"], "Month": 8, "Year": 2026, "Types": []}})

show("keepalive2", "global.keepAlive", {"timeout": 300, "active": True})
print("\n=== done ===")
