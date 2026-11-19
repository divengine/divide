# The MSIX package of divide, for the Microsoft Store (which signs it).
#
#   pwsh packaging/msix/build.ps1 -Version 0.1.0 -Exe dist/divide.exe -Out out/divide.msix `
#        -IdentityName Divengine.divide -Publisher "CN=..." -PublisherName Divengine [-Test]
#
# The identity (name, publisher, publisher's name) is the one Partner Center gives the product
# (Product management > Product identity). -Test signs a copy with a certificate made for the
# occasion, installs it and runs "divide --version" through its alias, then removes it all:
# the package given to the Store stays unsigned.
param(
    [Parameter(Mandatory)][string]$Version,
    [Parameter(Mandatory)][string]$Exe,
    [Parameter(Mandatory)][string]$Out,
    [string]$IdentityName = "Divengine.divide",
    [string]$Publisher = "CN=Divengine",
    [string]$PublisherName = "Divengine",
    [switch]$Test
)
$ErrorActionPreference = "Stop"

if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    throw "An MSIX version is numbers only (x.y.z, the Store adds .0): '$Version' is not one"
}

function Find-Tool([string]$name) {
    $found = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\$name" -ErrorAction SilentlyContinue |
        Sort-Object { [version]$_.Directory.Parent.Name } | Select-Object -Last 1
    if (-not $found) { throw "$name not found: the Windows SDK is needed" }
    $found.FullName
}

$here = $PSScriptRoot
$layout = Join-Path ([IO.Path]::GetTempPath()) ("divide-msix-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $layout | Out-Null
try {
    Copy-Item $Exe (Join-Path $layout "divide.exe")
    Copy-Item (Join-Path $here "Assets") (Join-Path $layout "Assets") -Recurse
    Copy-Item (Join-Path $here "..\..\LICENSE") $layout
    $manifest = Get-Content (Join-Path $here "AppxManifest.xml") -Raw
    $values = @{ IdentityName = $IdentityName; Publisher = $Publisher; PublisherName = $PublisherName; Version = "$Version.0" }
    foreach ($key in $values.Keys) {
        $manifest = $manifest.Replace("`$($key)", [Security.SecurityElement]::Escape($values[$key]))
    }
    Set-Content -Path (Join-Path $layout "AppxManifest.xml") -Value $manifest -Encoding utf8

    New-Item -ItemType Directory -Force -Path (Split-Path $Out) | Out-Null
    & (Find-Tool makeappx.exe) pack /o /d $layout /p $Out
    if ($LASTEXITCODE -ne 0) { throw "makeappx failed" }

    if ($Test) {
        $signed = Join-Path ([IO.Path]::GetTempPath()) "divide-test.msix"
        Copy-Item $Out $signed -Force
        $cert = New-SelfSignedCertificate -Type Custom -Subject $Publisher -KeyUsage DigitalSignature `
            -FriendlyName "divide MSIX test" -CertStoreLocation Cert:\CurrentUser\My `
            -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3", "2.5.29.19={text}")
        try {
            & (Find-Tool signtool.exe) sign /fd SHA256 /sha1 $cert.Thumbprint /s My $signed
            if ($LASTEXITCODE -ne 0) { throw "signtool failed" }
            $cer = Join-Path ([IO.Path]::GetTempPath()) "divide-test.cer"
            Export-Certificate -Cert $cert -FilePath $cer | Out-Null
            Import-Certificate -FilePath $cer -CertStoreLocation Cert:\LocalMachine\TrustedPeople | Out-Null
            Add-AppxPackage -Path $signed
            $alias = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps\divide.exe"
            $said = & $alias --version
            if ($LASTEXITCODE -ne 0 -or "$said" -ne "divide $Version") { throw "the installed package says '$said'" }
            Write-Host "The package installs and runs: $said"
            Get-AppxPackage -Name $IdentityName | Remove-AppxPackage
        } finally {
            Get-ChildItem Cert:\LocalMachine\TrustedPeople | Where-Object Thumbprint -eq $cert.Thumbprint | Remove-Item
            Remove-Item $cert.PSPath
            Remove-Item $signed -ErrorAction SilentlyContinue
        }
    }
} finally {
    Remove-Item $layout -Recurse -Force
}
