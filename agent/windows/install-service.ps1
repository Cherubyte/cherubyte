<#
.SYNOPSIS
  Installs the Cherubyte agent as a Windows service.

.DESCRIPTION
  The agent is one executable and a service registration. It needs no Python,
  no Docker and no interactive login: point it at a panel, give it the
  enrolment token that panel minted, and it reports from then on.

  Run from an elevated PowerShell.

.EXAMPLE
  .\install-service.ps1 -PanelUrl http://192.168.1.9:1001 -EnrolToken abc123 -Name sala
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $PanelUrl,
    [Parameter(Mandatory = $true)][string] $EnrolToken,
    [string] $Name = $env:COMPUTERNAME,
    [string] $InstallDir = "$env:ProgramFiles\Cherubyte Agent",
    [string] $ExePath
)

$ErrorActionPreference = 'Stop'
$ServiceName = 'CherubyteAgent'

if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
        ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this from an elevated PowerShell — registering a service needs it.'
}

if (-not $ExePath) { $ExePath = Join-Path $PSScriptRoot 'cherubyte-agent.exe' }
if (-not (Test-Path $ExePath)) {
    throw "cherubyte-agent.exe not found at $ExePath. Download it from the panel's Agents page, or pass -ExePath."
}

Write-Host "Installing to $InstallDir"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item -Path $ExePath -Destination (Join-Path $InstallDir 'cherubyte-agent.exe') -Force

# The state directory holds the key issued at enrolment. Without it the agent
# re-enrols on every start, and enrolment tokens are single-use — so the second
# start would fail. It is deliberately outside the install directory so an
# upgrade cannot wipe it.
$StateDir = Join-Path $env:ProgramData 'Cherubyte Agent'
New-Item -ItemType Directory -Force -Path $StateDir | Out-Null

# Settings live in the machine environment so the service picks them up, and so
# the token is not visible in the service's command line (where any user can
# read it with `sc qc` or Task Manager).
[Environment]::SetEnvironmentVariable('CHERUBYTE_AGENT_PANEL_URL',  $PanelUrl,   'Machine')
[Environment]::SetEnvironmentVariable('CHERUBYTE_AGENT_ENROL_TOKEN', $EnrolToken, 'Machine')
[Environment]::SetEnvironmentVariable('CHERUBYTE_AGENT_NAME',        $Name,       'Machine')
[Environment]::SetEnvironmentVariable('CHERUBYTE_AGENT_STATE_FILE',
    (Join-Path $StateDir 'agent.json'), 'Machine')

if (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) {
    Write-Host 'Service already exists — stopping it to upgrade'
    Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
    sc.exe delete $ServiceName | Out-Null
    Start-Sleep -Seconds 2
}

# The executable registers itself: it speaks the Service Control Manager
# protocol, and `sc.exe create` over a plain console exe would install fine and
# then fail on start with error 1053.
# LocalSystem, because the ARP sweep needs raw sockets. Everything else the
# agent does is outbound HTTP.
$exe = Join-Path $InstallDir 'cherubyte-agent.exe'
& $exe --startup auto install
if ($LASTEXITCODE -ne 0) { throw "Service registration failed ($LASTEXITCODE)." }
# Restart on failure rather than staying down: a network that is briefly gone
# is the normal case, not an error worth a silent stop.
sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/15000/restart/60000 | Out-Null

Start-Service -Name $ServiceName
Write-Host ''
Write-Host "Cherubyte agent installed and started as '$Name'." -ForegroundColor Green
Write-Host "  Panel:  $PanelUrl"
Write-Host "  State:  $StateDir"
Write-Host "  Health: http://127.0.0.1:1002/health"
Write-Host ''
Write-Host 'It should appear on the panel''s Agents page within a minute.'
