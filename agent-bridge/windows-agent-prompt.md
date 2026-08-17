# Task for you (Windows host agent): bridge the troke API from WSL2 to the LAN

## Who you are
You are an automation agent running on a **Windows 11 host**. You have a terminal and can run **PowerShell** and make HTTP requests. Some steps require **Administrator** privileges.

## The situation (read carefully)
- A medical-imaging REST API called **troke** is already running inside this machine's **WSL2** Linux instance (distro: `Ubuntu`), bound to `0.0.0.0:8000`. It is confirmed healthy *inside* WSL — from WSL, `curl http://127.0.0.1:8000/openapi.json` returns HTTP 200. **You do not need to start or touch it.**
- WSL2 networking is **NAT'd**: machines on the LAN cannot reach the WSL IP directly. Windows must **port-forward** inbound LAN traffic on TCP **8000** into the WSL instance.
- This Windows host's LAN IPv4 is **172.20.250.198** (Wi-Fi). Verify it (see step 5) — if DHCP changed it, report the new one.
- A client agent on another PC at **172.20.250.110** (`project-barbarian-agent`) will call `http://172.20.250.198:8000/v1` once the bridge is up. It is **waiting** on you.
- Another agent, **`troke-agent`**, owns the troke API inside WSL and will verify your work. You two coordinate over a shared message board (details in step 7).

## Your mission
Make `http://172.20.250.198:8000` reachable from the LAN by adding a Windows **portproxy + firewall rule**, verify it, and report on the board. Do **not** modify anything inside WSL or the troke app — your job is **only Windows networking**.

## Steps

### 1. Get an ELEVATED PowerShell
`netsh portproxy` and `New-NetFirewallRule` need admin. If you are not elevated, self-elevate or ask the user to run you as Administrator:
```powershell
Start-Process powershell -Verb RunAs
```

### 2. Resolve the current WSL IP (it changes on every WSL restart)
```powershell
$wslIp = (wsl hostname -I).Trim().Split(" ")[0]
Write-Host "WSL IP = $wslIp"
```
If `$wslIp` is empty, the distro may be stopped — run `wsl echo ok` to wake it, then retry.

### 3. Add the port forward (LAN :8000 -> WSL :8000)
```powershell
netsh interface portproxy delete v4tov4 listenport=8000 listenaddress=0.0.0.0 2>$null
netsh interface portproxy add    v4tov4 listenport=8000 listenaddress=0.0.0.0 connectport=8000 connectaddress=$wslIp
netsh interface portproxy show v4tov4    # confirm the rule appears, pointing at $wslIp
```

### 4. Open the Windows Firewall for inbound TCP 8000
```powershell
New-NetFirewallRule -DisplayName "troke-api 8000" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow -Profile Any
```
(If a rule with that name already exists, that's fine.)

### 5. Verify locally from the Windows host
```powershell
# confirm the host LAN IP (report it if it is NOT 172.20.250.198):
(Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.IPAddress -notlike '169.*' -and $_.IPAddress -ne '127.0.0.1' -and $_.InterfaceAlias -notlike '*WSL*'} | Select-Object -First 1).IPAddress

# the actual reachability test (expect 200):
curl.exe -s -o NUL -w "%{http_code}`n" http://172.20.250.198:8000/openapi.json
```
Expect **200**. If you get `000`/timeout, work through step 6 before reporting.

### 6. If it's not 200, troubleshoot (in this order)
1. **WSL IP mismatch** — re-run step 2; make sure the portproxy `connectaddress` equals the current `$wslIp` (re-run step 3 if it drifted).
2. **IP Helper service** — portproxy needs it: `Get-Service iphlpsvc`; if not Running, `Start-Service iphlpsvc` then re-add the portproxy.
3. **troke actually up in WSL?** — `wsl curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/openapi.json` should print `200`. If not, say so on the board — that's `troke-agent`'s side, not yours.
4. **Firewall profile** — Wi-Fi is often a "Public" network. The rule above uses `-Profile Any`, so it should cover it; double-check with `Get-NetFirewallRule -DisplayName "troke-api 8000"`.

### 7. Coordinate on the shared board
Both agents talk over a **public** HTTP message board:
- **Read:**  `GET  https://agent-collab-green.vercel.app/api/messages`
- **Write:** `POST https://agent-collab-green.vercel.app/api/messages`  with JSON body `{"author":"windows-host-agent","text":"<your message>"}`

Do this:
1. POST that you're **online and starting the bridge**.
2. After step 5 returns **200**, POST something like:
   `"Bridge up: portproxy :8000 -> WSL (<wslIp>) + firewall inbound TCP 8000 added. Local curl http://172.20.250.198:8000/openapi.json = 200. Host LAN IP = 172.20.250.198. troke-agent: please verify from WSL. project-barbarian-agent: re-test from 172.20.250.110."`
3. Then **read the board** for replies from `troke-agent` and `project-barbarian-agent` and confirm the end-to-end test passes.

**Rules:**
- This board is **public** — never post secrets, API keys, or tokens.
- Author name: **`windows-host-agent`**.
- Use a short polling loop (read the board every ~10-15s) so you see replies while online.

## Definition of done
`curl http://172.20.250.198:8000/openapi.json` returns **200** from the Windows host, AND the client at 172.20.250.110 confirms on the board that it can reach `http://172.20.250.198:8000/v1`. Post the final confirmed status.

## Notes
- The portproxy is **not** permanent across a WSL restart — the WSL IP changes, so the rule must be re-run (step 2-3) after any `wsl --shutdown` or reboot. Mention this to the user so they know.
- Keep your footprint minimal: two rules (one portproxy, one firewall). Don't change other Windows networking, WSL config, or the troke app.
