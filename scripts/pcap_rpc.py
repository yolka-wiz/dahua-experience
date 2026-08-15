#!/usr/bin/env python3
"""Parse nvr_traffic.pcap, extract HTTP POST bodies (Dahua RPC2 JSON) and
print method -> params so we can learn the exact call shapes the UI uses."""
import dpkt, sys, json, collections

SLL2 = getattr(dpkt, "sll2", None)

path = sys.argv[1] if len(sys.argv) > 1 else "/home/agent/nvr/nvr_traffic.pcap"
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 0  # 0 = all

calls = []          # (method, params_json_str)
config_keys = collections.Counter()
method_count = collections.Counter()

def handle_tcp(tcp, ts):
    data = tcp.data
    if not data:
        return
    # HTTP request? Look for POST + Content-Length
    if data[:4] == b"POST":
        try:
            head, _, body = data.partition(b"\r\n\r\n")
            clen = 0
            for line in head.split(b"\r\n"):
                if line.lower().startswith(b"content-length:"):
                    clen = int(line.split(b":")[1].strip())
            if clen and len(body) >= clen:
                payload = body[:clen]
                if b"RPC2" in head or payload[:1] in (b"{", b"["):
                    try:
                        obj = json.loads(payload)
                        if isinstance(obj, dict) and "method" in obj:
                            m = obj["method"]
                            method_count[m] += 1
                            params = obj.get("params")
                            # redact session
                            obj.pop("session", None)
                            calls.append((m, json.dumps(params, ensure_ascii=False, sort_keys=True)))
                            if m == "configManager.getConfig" and isinstance(params, dict) and "name" in params:
                                config_keys[params["name"]] += 1
                    except Exception:
                        pass
        except Exception:
            pass

with open(path, "rb") as f:
    pcap = dpkt.pcap.Reader(f)
    try:
        for ts, buf in pcap:
            try:
                if SLL2 is not None and pcap.datalink() == 276:
                    link = SLL2.SLL2(buf)
                    ip = link.data
                else:
                    eth = dpkt.ethernet.Ethernet(buf)
                    ip = eth.data
                if isinstance(ip, dpkt.ip.IP):
                    if isinstance(ip.data, dpkt.tcp.TCP):
                        handle_tcp(ip.data, ts)
            except Exception:
                continue
    except dpkt.dpkt.NeedData:
        pass

print(f"=== RPC method counts ({sum(method_count.values())} calls) ===")
for m, c in method_count.most_common():
    print(f"{c:4d}  {m}")

print(f"\n=== configManager.getConfig keys ({sum(config_keys.values())} reads) ===")
for k, c in config_keys.most_common():
    print(f"{c:4d}  {k}")

print(f"\n=== Unique param shapes (first occurrence each) ===")
seen = set()
shown = 0
for m, p in calls:
    key = (m, p)
    if key in seen:
        continue
    seen.add(key)
    shown += 1
    if limit and shown > limit:
        break
    print(f"\n--- {m}")
    print(p[:600])
