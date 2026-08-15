---
name: network-device-automation
description: "Automate config collection, diagnostics, and maintenance on network devices using legacy protocols — telnet, SSH (old IOS), and WinRM. Use when backing up switch/firewall configs, fixing SSH on legacy Cisco gear, or remote-diagnosing Windows machines that only support WinRM."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [network, cisco, telnet, ssh, winrm, automation]
    related_skills: [systematic-debugging]
---

# Network Device Automation

## Overview

Many enterprise network devices (Cisco Catalyst 2960S, FortiGate, older Windows servers) only support legacy protocols for remote access — telnet, SSHv2 with weak algorithms, or WinRM. Modern clients (OpenSSH 10.3+, Paramiko 5.0) have removed support for these legacy algorithms, causing seemingly inexplicable failures. This skill covers the techniques for automating against these devices without upgrading them.

## When to Use

- Collecting running configs from Cisco switches (telnet or SSH)
- Backing up Fortigate firewalls via SSH
- Regenerating SSH RSA keys on old IOS switches to enable modern SSH clients
- Remote-diagnosing Windows machines via WinRM (AppX packages, services, winget)
- Any situation where a device only speaks telnet or SSHv2 with `diffie-hellman-group1-sha1`

**Don't use for:** Modern Linux servers with OpenSSH 8.8+ where standard SSH works. Modern network gear with SSH key exchange support (use standard `ssh` or `paramiko`).

## Telnet Automation (Cisco IOS)

Python socket-based telnet works reliably even when `telnetlib` is removed (Python 3.13+). Key pattern:

**CRITICAL telnet lesson (learned 2026-08):** do NOT use prompt-matching reads with a stale buffer. If the buffer still holds the previous prompt, `drain_until(prompt=True)` returns immediately and clears the buffer, so the command you just sent gets its output read during the NEXT command — a one-command lag that makes outputs appear swapped/empty. The reliable pattern is the "quiet-window" read: send the command, wait ~0.8-1.5s, then read until 1.5-2s of silence (bounded). This is the pattern in `/home/agent/nvr/full_vlan40_sweep3.py` and it never misattributes output. Prompt matching only works if you fully consume the buffer after every command.

**Beware the eaten first char:** sending a command right after a previous read can drop its first character (e.g. `how running-config`). Settle the line first: send a bare `\r\n`, drain, THEN send the command.

**Timing:** a per-switch full sweep (mac table + interfaces + PoE + running-config) takes ~45-60s per switch over telnet. Run multi-switch sweeps in background with `terminal(background=true)` — foreground hits the 300s cap at ~5 switches. Verify each change by re-reading `show running-config | include ...` afterwards; never trust the apply script's own "ok".

## Camera-to-port mapping + descriptions (Cisco + Dahua NVR)

Proven workflow for labeling camera ports from a Dahua NVR + Cisco floor switches:

1. **Get camera inventory from the NVR** (see dahua-h5-rpc-login skill): `cam_status.py` writes cam_inventory.json with per-camera `mac` (lowercase colon format), `title`, `channel`, `ip`.
2. **Sweep every switch** (full_vlan40_sweep3.py): `show mac address-table vlan 40`, `show interfaces status`, `show power inline`, `show running-config`. Correlate switch MACs (dotted `e424.6c9a.7aca`) against inventory MACs (colon format, strip both `:` and `.`, lowercase) to map camera → port.
3. **Beware trunk ports**: many cameras appear on the uplink trunk port (e.g. Gi1/0/49) — those are NOT directly connected. Only access ports with a single camera MAC are direct connections worth labeling.
4. **Apply descriptions** (apply_desc.py): `configure terminal` → `interface GiX` → `description cam <TITLE>` → `end`. Running-config only unless told to `write mem`. Back up configs FIRST (network-config-backup skill, one .cfg per switch).
5. **Verify** (verify_desc.py): re-read `show running-config | include cam ` from each switch and confirm every description landed. The apply script's "ok" is not proof.

**PoE diagnosis pattern (camera offline):** a port with PoE ON (~15.4W, device "Ieee PD") + link up + NO MAC learned + high input errors/CRC = camera physically present but its data path is dead (bad cable pair or dead camera NIC). A port with PoE OFF + notconnect = nothing plugged in. Check both before blaming the NVR: NVR "Unconnect" + no ping + port shows these symptoms = physical layer, not NVR config.

**VLAN 40 access ports on SW-F1 (verified 2026-08):** Gi1/0/42=F1_CAM2, 43=RAHMANI-VOIP, 44=F1_CAM1, 46=REAR_L (PoE on, no MAC = dead cam/cable), 47=empty, 48=REAR_R. Camera descriptions "cam X" written on all 30 direct camera ports across SW-F0..F5 2026-08-13.

```python
import socket, time

IAC = bytes([255])
DONT = bytes([254])
DO   = bytes([253])
WONT = bytes([252])
WILL = bytes([251])
SE   = bytes([240])

def recv_filter(sock, timeout=5):
    """Receive and strip telnet negotiation sequences."""
    data = b""
    sock.settimeout(timeout)
    try:
        while True:
            chunk = sock.recv(4096)
            if not chunk: break
            data += chunk
    except socket.timeout: pass
    # Filter IAC sequences
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
    return filtered.decode('utf-8', errors='replace')
```

### Cisco Telnet Login Sequence
```
connect → receive "Username:" → send username → receive "Password:" → send password → receive "#" prompt
```

### Essential First Command: Disable Paging
```
terminal length 0
```
Always send this first on Cisco switches to avoid `--More--` prompts. If you forget, the script will hang waiting for output.

### Handling Interactive Prompts
Commands like `crypto key generate rsa` may prompt `"Do you really want to replace them? [yes/no]:"`. Detect and respond with `"yes"` + newline.

### Multi-Version Command Syntax
- **IOS 12.2**: `crypto key generate rsa general-keys modulus 2048`
- **IOS 15.x**: `crypto key generate rsa modulus 2048` or `crypto key generate rsa general-keys modulus 2048`

Both versions work on 15.x, but 12.2 **requires** `general-keys`.

## Legacy SSH Workarounds

Old Cisco IOS (12.2/15.0) only supports:
- **KEX**: `diffie-hellman-group1-sha1` (removed from OpenSSH 10.3+ and Paramiko 5.0)
- **Host key**: `ssh-rsa` (RSA with SHA-1, deprecated in OpenSSH 8.8+)
- **Ciphers**: `aes128-cbc, aes192-cbc, aes256-cbc, 3des-cbc` (CBC mode, disabled by default)
- **MACs**: `hmac-sha1, hmac-sha1-96`

### OpenSSH CLI Workaround
```bash
ssh -oKexAlgorithms=+diffie-hellman-group1-sha1 \
    -oHostKeyAlgorithms=+ssh-rsa \
    -oCiphers=+aes128-cbc \
    -oMACs=+hmac-sha1 \
    -o StrictHostKeyChecking=no \
    -o UserKnownHostsFile=/dev/null \
    a.alavi@192.168.1.100
```

### SSH Config Block
```
Host 192.168.1.10? 192.168.1.110
    KexAlgorithms +diffie-hellman-group1-sha1
    HostKeyAlgorithms +ssh-rsa
    Ciphers +aes128-cbc
    MACs +hmac-sha1
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
    PreferredAuthentications password
```

### Paramiko is NOT an Option
Paramiko 5.0 removed `kex_group1` entirely. Even overriding `SecurityOptions.kex` won't add it back because the implementation module was deleted. Use command-line `ssh` (OpenSSH with `+` flags) instead.

### Force Password via Terminal
SSH over `stdin` pipe won't get a TTY for password prompt. Use the terminal tool directly (which provides a PTY) when you need to test or run SSH interactively. `execute_code` subprocess will timeout because SSH can't prompt for password.

### SSH Key Generation Fix (Cisco IOS)
If OpenSSH 10.3+ gives `"Invalid key length"` on an otherwise-negotiated SSH connection, the switch's RSA host key is too short (512-bit default on old IOS). Fix via telnet:

```python
# On IOS 12.2:
send("crypto key generate rsa general-keys modulus 2048")
# On IOS 15.x:
send("crypto key generate rsa modulus 2048")
# Then:
send("write memory")
```

The key generation takes 20-60 seconds on a 2960S. The confirm prompt `"[yes/no]"` appears before generation starts.

### IOS Key Size Reality
- **12.2(55)SE3**: Supports up to 2048-bit with `general-keys` syntax
- **15.0(2)SE11**: Supports up to 2048-bit
- **15.2(2)E9 / 15.2(4)E10**: Supports up to 2048-bit
- Default keys are 512-bit — always regenerate

### SSH Commands to Verify
```
show ip ssh                  → shows enabled version, auth methods, algorithms
show crypto key mypubkey rsa → shows key names and DER-encoded data
show ssh                     → shows active sessions
```

## WinRM Remote Diagnostics

For Windows machines that only have WinRM enabled (no RDP, no SSH):

```python
import winrm
sess = winrm.Session('http://<host>:5985/wsman',
                     auth=('username', 'password'),
                     transport='ntlm')
r = sess.run_ps('command')
out = r.std_out.decode('utf-8', errors='replace')
```

### Common WinRM Patterns

**AppX Package diagnostics:**
```powershell
Get-AppxPackage -Name "*snipping*" -AllUsers | Format-List *
Get-AppxPackage -Name "*ScreenSketch*" -AllUsers | Format-List *
```

**Register a package for current user:**
```powershell
Add-AppxPackage -Register "C:\Program Files\WindowsApps\Microsoft.ScreenSketch_*\AppxManifest.xml" -DisableDevelopmentMode
```

**Check if winget is available:**
```powershell
Get-ChildItem "C:\Program Files\WindowsApps" -Recurse -Filter "winget.exe" -ErrorAction SilentlyContinue
```

### WinRM Limitations
- **GUI apps cannot be launched** via WinRM — `Start-Process` for GUI apps will fail with "The operation attempted is not supported"
- **winget.exe** may exist in `C:\Program Files\WindowsApps\` but fail with "Access is denied" because the WindowsApps folder has restrictive ACLs that don't resolve properly in non-interactive WinRM sessions
- **App Execution Aliases** (stubs in `%LOCALAPPDATA%\\Microsoft\\WindowsApps\\`) don't work in WinRM sessions
- Native PowerShell errors return as CLIXML which pollutes stderr — check `r.std_err` for `#< CLIXML` and strip it
- **`_x005F_` path encoding bug**: When `pywinrm` sends PowerShell commands containing `_x` in file paths (e.g. AppX package folders like `Microsoft.ScreenSketch_11.2307.52.0_x64__8wekyb3d8bbwe`), the `_x` sequence gets XML-escaped to `_x005F_` (the Unicode/XML escape for underscore `_`). This causes `Add-AppxPackage -Register` to fail with "Cannot find path".
  - **Workaround 1:** Pass the path through a PowerShell environment variable: `$env:PKG = 'C:\\...'; Add-AppxPackage -Register "$env:PKG\\AppxManifest.xml"`
  - **Workaround 2:** Use `sess.run_cmd()` (cmd.exe) instead of `sess.run_ps()` for path-sensitive operations — cmd.exe doesn't apply XML encoding
- **AppX user-profile deployment limitation**: In non-interactive WinRM sessions, `Add-AppxPackage -Register` registers the package at system level (Status: Ok) but `PackageUserInformation` remains empty `{}`. The package **never deploys to any user's profile** from a WinRM session. This is a fundamental limitation — the AppX provisioning pipeline requires interactive user profile loading.
  - **Fix 1:** Log out and log back in on the target machine
  - **Fix 2:** Run registration via `schtasks` with the `/it` (interactive) flag as the console user:
    ```powershell
    schtasks /create /tn "DeployAppX" /tr "powershell -Command Add-AppxPackage -Register '...\\AppxManifest.xml' -DisableDevelopmentMode" /sc once /st 23:59 /ru "DOMAIN\\User" /it /f
    schtasks /run /tn "DeployAppX"
    ```
- **`Remove-AppxPackage -AllUsers`** deletes the package files physically from `C:\Program Files\WindowsApps\`, not just the registration. Do NOT use `-AllUsers` if the package files are the only copy available.
- **Common AppX error 0x87E10BC6**: "Cannot create the process for package because an error was encountered while preparing for activation." Usually means the package is registered but not deployed to the user profile, or the executable referenced in the manifest doesn't match the files on disk.

### Windows Printer Troubleshooting via WinRM

```powershell
# Full printer details
Get-Printer -Name "Printer Name" | Format-List *
# CIM status (gives numeric codes)
Get-CimInstance Win32_Printer -Filter "Name = 'Printer Name'"
```

**Key CIM status codes:**

| Field | Values | Meaning |
|-------|--------|---------|
| `PrinterStatus` | 3=Idle, 4=Printing/Unknown | Operational state |
| `DetectedErrorState` | 0=NoError, 2=Error | Error condition |
| `PrinterState` | 0=Idle, 1024=IO_ACTIVE | Internal state machine |
| `WorkOffline` | True/False | Manually set offline |
| `JobCount` | N | Pending jobs |

**Stuck print jobs** (most common cause of non-printing):
```powershell
# Check queue
Get-PrintJob -PrinterName "Printer Name" | Select-Object Id, DocumentName, JobStatus
# Clear stuck job(s)
Stop-Service Spooler -Force
Remove-Item "C:\Windows\System32\spool\PRINTERS\*" -Force
Start-Service Spooler
```
After cleanup the printer transitions from `PrinterState=1024` back to `0` (Idle) with `DetectedErrorState=0` (NoError).

**Driver mismatch** (second most common cause):
- **v4 drivers** (MajorVersion=4): "Class Drivers" — minimal, can cause issues with older printers
- **v3 drivers** (MajorVersion=3): Full manufacturer drivers — more reliable for non-modern printers
```powershell
# Check installed drivers
Get-PrinterDriver -Name "*P2035*" | Select-Object Name, MajorVersion
# Switch driver
Set-Printer -Name "Printer Name" -DriverName "HP LaserJet P2035"
Restart-Service Spooler -Force
```

## Common Pitfalls

1. **Telnet IAC handling missing.** If the raw output contains garbled characters like `\ufffd\ufffd\ufffd`, you're not filtering IAC negotiation sequences. Always strip them with the recv_filter pattern above.

2. **`--More--` pagination blocking.** Always send `terminal length 0` first on Cisco devices. Without it, long output (show running-config) will hang indefinitely waiting for a space/enter.

3. **2048-bit key generation timeout on 12.2 IOS.** The 12.2 IOS takes 50-60 seconds for 2048-bit RSA generation vs 20-30 seconds on 15.x. Set recv timeouts to at least 120 seconds.

4. **Assuming `yes/no` prompt always appears.** Some IOS versions skip the replacement prompt if the old key was already removed (`crypto key zeroize rsa`). The `crypto key zeroize` command itself also prompts — be ready for that too.

5. **WinRM CLIXML noise.** Non-error output sometimes shows up in stderr wrapped in CLIXML. Strip `<Objs Version=...` from stderr before reporting errors.

6. **No TTY for SSH from subprocess.** SSH needs a terminal for password prompts. Use the terminal tool (which provides PTY) or install sshpass. Do NOT use `subprocess.run` with stdin pipe for SSH password entry.

## Related Files

- `references/commands-and-errors.md` — common Cisco CLI commands and error message interpretations
- `references/printer-diagnostics.md` — Windows printer troubleshooting via WinRM (stuck jobs, driver mismatch)
- `references/winrm-appx-troubleshooting.md` — AppX deployment limitations in WinRM, `_x005F_` path encoding bug, SnippingTool/ScreenSketch repair

## Verification Checklist

- [ ] Telnet: can connect, login, and receive command output without garbled characters
- [ ] SSH: `ssh -oKexAlgorithms=+diffie-hellman-group1-sha1 <host>` connects and runs commands
- [ ] SSH keys: `show crypto key mypubkey rsa` shows key >= 2048-bit modulus
- [ ] Config saved: `write memory` returns `[OK]`
- [ ] WinRM: `sess.run_ps('hostname')` returns the hostname without CLIXML errors
