#!/usr/bin/env python3
"""Write camera names into port descriptions on floor switches.
Applies to running-config only (no write mem). Backup configs first!
"""
import socket, time, sys, os

USER = "a.alavi"
PASS = os.environ.get("SW_PASS", "")  # set from vault: vault-get sw1

# switch -> {port: description}
PLAN = {
    "192.168.1.100": {  # SW-F0
        "Gi1/0/5":  "cam FRONT_L",
        "Gi1/0/6":  "cam FRONT_R",
        "Gi1/0/7":  "cam F0_CAM1",
        "Gi1/0/8":  "cam F0_CAM2",
        "Gi1/0/9":  "cam F0_CAM4",
        "Gi1/0/10": "cam F-1_CAM1",
        "Gi1/0/11": "cam F-1_NAMAZ",
        "Gi1/0/12": "cam F0_CAM3",
        "Gi1/0/13": "cam F-1_STOR1",
        "Gi1/0/14": "cam F-1_RESTORAN",
        "Gi1/0/15": "cam F-1_STOR4",
        "Gi1/0/16": "cam F-1_STOR3",
        "Gi1/0/17": "cam F-1_STOR2",
        "Gi1/0/21": "cam F0_SEC",
    },
    "192.168.1.101": {  # SW-F1
        "Gi1/0/42": "cam F1_CAM2",
        "Gi1/0/44": "cam F1_CAM1",
        "Gi1/0/46": "cam REAR_L (offline)",
        "Gi1/0/48": "cam REAR_R",
    },
    "192.168.1.102": {  # SW-F2
        "Gi1/0/42": "cam F2_CAM2",
        "Gi1/0/44": "cam F2_CAM1",
    },
    "192.168.1.103": {  # SW-F3
        "Gi1/0/32": "cam F3_CAM2",
        "Gi1/0/34": "cam F3_CAM1",
        "Gi1/0/36": "cam F3_SERVER",
    },
    "192.168.1.104": {  # SW-F4
        "Gi1/0/42": "cam F4_CAM2",
        "Gi1/0/44": "cam F4_CAM1",
    },
    "192.168.1.105": {  # SW-F5
        "Gi1/0/10": "cam F5_CAM2",
        "Gi1/0/12": "cam F5_CAM1",
        "Gi1/0/14": "cam ROOF_CAM1",
        "Gi1/0/16": "cam ROOF_R",
        "Gi1/0/18": "cam ROOF_L",
        "Gi1/0/20": "cam ASANSOR",
    },
}

IAC = bytes([255]); DONT = bytes([254]); DO = bytes([253])
WONT = bytes([252]); WILL = bytes([251]); SB = bytes([250]); SE = bytes([240])

def recv_filter(sock, timeout=5):
    data = b""
    sock.settimeout(timeout)
    try:
        while True:
            chunk = sock.recv(65536)
            if not chunk: break
            data += chunk
    except socket.timeout: pass
    filtered = b""
    i = 0
    while i < len(data):
        if data[i:i+1] == IAC:
            if i+1 < len(data):
                cmd = data[i+1:i+2]
                if cmd in [DO, DONT, WILL, WONT] and i+2 < len(data):
                    opt = data[i+2:i+3]
                    if cmd in [DO, WILL]:
                        sock.send(IAC + (WONT if cmd == DO else DONT) + opt)
                    i += 3; continue
                elif cmd == SB:
                    end = data.find(IAC + SE, i)
                    if end != -1: i = end + 2; continue
                    else: break
                elif cmd == SE: i += 2; continue
                else: i += 2; continue
            else: break
        else:
            filtered += data[i:i+1]; i += 1
    return filtered.decode("utf-8", errors="replace")

def send(sock, cmd, wait=0.8):
    sock.sendall((cmd + "\r\n").encode())
    time.sleep(wait)
    return recv_filter(sock)

def login(host):
    s = socket.create_connection((host, 23), timeout=10)
    out = recv_filter(s, timeout=8)
    if "sername" in out:
        s.sendall((USER + "\r\n").encode()); time.sleep(1)
        out = recv_filter(s, timeout=4)
    if "assword" in out:
        s.sendall((PASS + "\r\n").encode()); time.sleep(1.5)
        out = recv_filter(s, timeout=5)
    if ">" in out and "#" not in out:
        s.sendall(b"enable\r\n"); time.sleep(1)
        out = recv_filter(s, timeout=4)
        if "assword" in out:
            s.sendall((PASS + "\r\n").encode()); time.sleep(1.5)
            out = recv_filter(s, timeout=5)
    send(s, "terminal length 0", wait=1)
    return s

def apply_switch(host, port_desc):
    s = login(host)
    results = {}
    send(s, "configure terminal", wait=1)
    for port, desc in sorted(port_desc.items()):
        out = send(s, f"interface {port}", wait=0.6)
        out = send(s, f"description {desc}", wait=0.6)
        if "Invalid" in out or "%" in out.split("\r\n")[-2] if "\r\n" in out else "%" in out:
            results[port] = f"ERROR: {out.strip()[-80:]}"
        else:
            results[port] = "ok"
    send(s, "end", wait=0.8)
    send(s, "exit", wait=0.5)
    s.close()
    return results

def verify(host, ports):
    s = login(host)
    send(s, "show running-config interface " + " ".join(ports) if False else "show running-config | include description", wait=3)
    out = recv_filter(s, timeout=6)
    s.sendall(b"exit\r\n")
    s.close()
    return out

if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for host, pd in PLAN.items():
        if only and only != host:
            continue
        print(f"\n== {host} ==", flush=True)
        try:
            res = apply_switch(host, pd)
            for p, r in sorted(res.items()):
                print(f"  {p:<8} {pd[p]:<22} -> {r}", flush=True)
        except Exception as e:
            print(f"  FAIL: {e}", flush=True)
