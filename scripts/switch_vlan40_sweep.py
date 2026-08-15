#!/usr/bin/env python3
"""Full VLAN40 sweep v3: quiet-window reads (proven pattern), backups + camera map."""
import socket, time, json, re, os, sys

SWITCHES = [
    ("192.168.1.100", "SW-F0"),
    ("192.168.1.101", "SW-F1"),
    ("192.168.1.102", "SW-F2"),
    ("192.168.1.103", "SW-F3"),
    ("192.168.1.104", "SW-F4"),
    ("192.168.1.105", "SW-F5"),
    ("192.168.1.110", "SW-CORE"),
]
USER = "a.alavi"
PASS = os.environ.get("SW_PASS", "")  # set from vault: vault-get sw1
BACKUP_DIR = "/home/agent/nvr/backups"
os.makedirs(BACKUP_DIR, exist_ok=True)

cams = json.load(open("/home/agent/nvr/cam_inventory.json"))
by_mac = {}
for c in cams:
    mac = (c.get("mac") or "").lower().replace(":", "")
    if mac:
        by_mac[mac] = c

IAC = bytes([255]); DONT = bytes([254]); DO = bytes([253])
WONT = bytes([252]); WILL = bytes([251]); SB = bytes([250]); SE = bytes([240])

def cisco_key(m):
    return m.replace(".", "").lower()[:12]

def recv_filter(sock, timeout=6):
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

def send(sock, cmd, wait=1.0):
    sock.sendall((cmd + "\r\n").encode())
    time.sleep(wait)
    return recv_filter(sock)

def telnet_login(host, user, pw, timeout=10):
    s = socket.create_connection((host, 23), timeout=timeout)
    out = recv_filter(s, timeout=8)
    if "sername" in out:
        s.sendall((user + "\r\n").encode()); time.sleep(1)
        out = recv_filter(s, timeout=4)
    if "assword" in out:
        s.sendall((pw + "\r\n").encode()); time.sleep(1.5)
        out = recv_filter(s, timeout=5)
    if ">" in out and "#" not in out:
        s.sendall(b"enable\r\n"); time.sleep(1)
        out = recv_filter(s, timeout=4)
        if "assword" in out:
            s.sendall((pw + "\r\n").encode()); time.sleep(1.5)
            out = recv_filter(s, timeout=5)
    send(s, "terminal length 0", wait=1)
    return s

def run_switch(ip, name):
    s = telnet_login(ip, USER, PASS)
    r = {}
    # quiet-window read per command: keep reading until 1.5s of silence
    def qcmd(c, min_wait=0.8, quiet=1.5, max_t=15):
        s.sendall((c + "\r\n").encode())
        time.sleep(min_wait)
        data = b""
        s.settimeout(0.5)
        end = time.time() + max_t
        while time.time() < end:
            try:
                chunk = s.recv(65536)
                if not chunk:
                    break
                data += chunk
                last = time.time()
            except socket.timeout:
                if time.time() - (last if 'last' in dir() else 0) > quiet and data:
                    break
                continue
        return data.decode(errors="replace")
    r["show mac address-table vlan 40"] = qcmd("show mac address-table vlan 40")
    r["show interfaces status"] = qcmd("show interfaces status")
    r["show power inline"] = qcmd("show power inline")
    r["show running-config"] = qcmd("show running-config", min_wait=1.5, quiet=2.0, max_t=25)
    s.sendall(b"exit\r\n")
    s.close()
    return r

def process(name, ip, r):
    print(f"\n{'='*60}\n== {name} @ {ip} ==", flush=True)
    cfg = r.get("show running-config", "")
    if cfg.strip() and "Invalid input" not in cfg and "ERROR" not in cfg:
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = f"{BACKUP_DIR}/{name}_{ts}.cfg"
        with open(path, "w") as f:
            f.write(f"! {name} @ {ip} backup {ts}\n" + cfg)
        print(f"  backup saved: {path} ({len(cfg)} chars)", flush=True)
    else:
        print(f"  WARN: running-config empty/invalid: {cfg[:120]!r}", flush=True)

    port_cams = {}
    for line in r.get("show mac address-table vlan 40", "").splitlines():
        m = re.match(r"\s*40\s+([0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4})\s+\S+\s+(Gi\d+/\d+/\d+)\s*$", line)
        if m:
            key = cisco_key(m.group(1))
            c = by_mac.get(key)
            if c:
                port_cams.setdefault(m.group(2), []).append(c)

    pnames, poe = {}, {}
    for line in r.get("show interfaces status", "").splitlines():
        m = re.match(r"(Gi1/\d+/\d+)\s+(\S+)?\s+(\S+)\s+(\S+)", line)
        if m:
            pnames[m.group(1)] = {"name": m.group(2) or "", "status": m.group(3) or ""}
    for line in r.get("show power inline", "").splitlines():
        m = re.match(r"(Gi1/\d+/\d+)\s+(\S+)\s+(\S+)\s+([\d.]+)\s+(\S+)", line)
        if m:
            poe[m.group(1)] = {"state": m.group(2), "class": m.group(3), "watts": m.group(4), "device": m.group(5)}

    print(f"  cameras directly matched: {sum(len(v) for v in port_cams.values())} on {len(port_cams)} ports", flush=True)
    for port in sorted(port_cams, key=lambda p: int(p.split("/")[-1])):
        for c in port_cams[port]:
            st = pnames.get(port, {}).get("status", "?")
            po = poe.get(port, {})
            print(f"    {port:<8} {c['title'][:18]:<18} ch{c['channel']:<3} {c['ip']:<16} status={st:<12} poe={po.get('watts','?')}W {po.get('device','')}", flush=True)
    return port_cams

if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for ip, name in SWITCHES:
        if only and only != ip:
            continue
        print(f"== connecting {name} @ {ip} ==", flush=True)
        try:
            r = run_switch(ip, name)
            process(name, ip, r)
        except Exception as e:
            print(f"== {name} FAIL: {e}", flush=True)
