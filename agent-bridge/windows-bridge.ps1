# Run ONCE in an ELEVATED PowerShell on Windows (right-click > Run as administrator).
# Forwards LAN traffic on :8765 into the WSL2 instance and opens the firewall, so the
# other PC can reach the relay at  http://<this-windows-LAN-ip>:8765.
# Re-run this after a WSL restart — the WSL IP changes and the rule goes stale.

$port  = 8765
$wslIp = (wsl hostname -I).Trim().Split(" ")[0]

netsh interface portproxy delete v4tov4 listenport=$port listenaddress=0.0.0.0 2>$null | Out-Null
netsh interface portproxy add    v4tov4 listenport=$port listenaddress=0.0.0.0 connectport=$port connectaddress=$wslIp

New-NetFirewallRule -DisplayName "agent-relay $port" -Direction Inbound -LocalPort $port `
    -Protocol TCP -Action Allow -ErrorAction SilentlyContinue | Out-Null

$lan = (Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object { $_.IPAddress -notlike '169.*' -and $_.IPAddress -ne '127.0.0.1' -and $_.InterfaceAlias -notlike '*WSL*' } |
        Select-Object -First 1).IPAddress
Write-Host "Bridge ready:  WSL $wslIp  ->  http://$lan`:$port  (give this URL to the other agent)"
