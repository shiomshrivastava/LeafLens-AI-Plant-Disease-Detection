# Run PowerShell AS ADMINISTRATOR in backend folder, once:
# powershell -ExecutionPolicy Bypass -File .\SETUP_LAN_FIREWALL.ps1
# Only allows devices on the SAME LOCAL SUBNET on TRUSTED PRIVATE Wi-Fi.
$ErrorActionPreference = 'Stop'
$me = [Security.Principal.WindowsIdentity]::GetCurrent()
$admin = New-Object Security.Principal.WindowsPrincipal($me)
if (-not $admin.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host 'Please open PowerShell as Administrator before running this script.' -ForegroundColor Red
    exit 1
}
$rules = @(
    @{ Name = 'LeafLens IoT API - Private LAN'; Protocol = 'TCP'; Port = '8000' },
    @{ Name = 'LeafLens Discovery - Private LAN'; Protocol = 'UDP'; Port = '42177' }
)
foreach ($r in $rules) {
    Get-NetFirewallRule -DisplayName $r.Name -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    New-NetFirewallRule -DisplayName $r.Name -Direction Inbound -Action Allow -Protocol $r.Protocol -LocalPort $r.Port -Profile Private -RemoteAddress LocalSubnet | Out-Null
    Write-Host ('Enabled ' + $r.Protocol + ' port ' + $r.Port + ' for Private local subnet only.') -ForegroundColor Green
}
Write-Host ''
Write-Host 'Current Wi-Fi network category:'
Get-NetConnectionProfile | Where-Object { $_.InterfaceAlias -eq 'Wi-Fi' } | Format-Table InterfaceAlias, Name, NetworkCategory -AutoSize
Write-Host 'If your OWN HOME or OWN PHONE HOTSPOT shows Public, mark that trusted connection Private in Windows Network Settings.'
Write-Host 'Do not mark unknown/public Wi-Fi networks Private.'
