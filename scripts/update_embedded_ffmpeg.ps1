<#
.SYNOPSIS
Installs or refreshes the embedded FFmpeg (bin\ffmpeg.exe, bin\ffprobe.exe) from GyanD builds.

.DESCRIPTION
Three modes:

  (default)  Install the LATEST GyanD release that has an essentials ZIP, then record it
             in scripts\ffmpeg_release.json (tag, asset, archive SHA256). Commit that file:
             it is what CI and release builds install.
  -Tag X     Install that exact GyanD release (e.g. a rollback to 9.0.1) and record it.
  -Pinned    Install exactly the release recorded in scripts\ffmpeg_release.json and verify
             the archive against the SHA256 stored there. Never writes the pin file and
             never looks at newer releases: this is the mode CI uses, so a release build
             can never change FFmpeg behind your back.

-CheckOnly answers from API metadata alone and downloads nothing.
#>
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "Medium")]
param(
    [string]$ReleasesApiUrl = "https://api.github.com/repos/GyanD/codexffmpeg/releases?per_page=20",
    [string]$Tag,
    [switch]$Pinned,
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
# Windows PowerShell 5.1 renders a progress bar per received chunk, which makes a
# ~115 MB Invoke-WebRequest crawl. Nothing reads it, so turn it off.
$ProgressPreference = "SilentlyContinue"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BinDir = Join-Path $ProjectRoot "bin"
$FfmpegPath = Join-Path $BinDir "ffmpeg.exe"
$FfprobePath = Join-Path $BinDir "ffprobe.exe"
$PinFilePath = Join-Path $PSScriptRoot "ffmpeg_release.json"
$ReleaseByTagApiUrl = "https://api.github.com/repos/GyanD/codexffmpeg/releases/tags/"
$UserAgent = "AccessibleMediaConverter-FFmpeg-Updater"

if ($Pinned -and $Tag) {
    throw "-Pinned and -Tag are mutually exclusive: -Pinned installs the tag recorded in $PinFilePath."
}

function Get-ApiHeaders {
    $headers = @{
        "Accept"     = "application/vnd.github+json"
        "User-Agent" = $UserAgent
    }
    # In GitHub Actions, the job token lifts the anonymous API quota (60 requests/hour
    # per IP, shared by every job on the runner's address).
    if ($env:GITHUB_TOKEN) {
        $headers["Authorization"] = "Bearer $($env:GITHUB_TOKEN)"
    }
    return $headers
}

function Read-PinFile {
    if (-not (Test-Path -LiteralPath $PinFilePath)) {
        throw "Pin file not found: $PinFilePath. Run this script without -Pinned once to create it."
    }
    $pin = Get-Content -LiteralPath $PinFilePath -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($field in @("tag", "asset", "sha256")) {
        if (-not ($pin.PSObject.Properties.Name -contains $field) -or -not [string]$pin.$field) {
            throw "Pin file $PinFilePath is missing the '$field' field."
        }
    }
    if ([string]$pin.sha256 -notmatch '^[0-9a-fA-F]{64}$') {
        throw "Pin file $PinFilePath has an invalid sha256: $($pin.sha256)"
    }
    return $pin
}

function Write-PinFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$TagName,
        [Parameter(Mandatory = $true)]
        [string]$AssetName,
        [Parameter(Mandatory = $true)]
        [string]$Sha256
    )

    $Sha256 = $Sha256.ToLowerInvariant()
    if (Test-Path -LiteralPath $PinFilePath) {
        $existing = Get-Content -LiteralPath $PinFilePath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($existing.tag -eq $TagName -and $existing.asset -eq $AssetName -and $existing.sha256 -eq $Sha256) {
            Write-Host "Pin file already records $TagName."
            return
        }
    }

    if ($WhatIfPreference) {
        Write-Host "What if: would record FFmpeg release $TagName in $PinFilePath"
        return
    }

    $json = @"
{
  "tag": "$TagName",
  "asset": "$AssetName",
  "sha256": "$Sha256"
}
"@
    [System.IO.File]::WriteAllText($PinFilePath, $json.Replace("`r`n", "`n") + "`n", [System.Text.UTF8Encoding]::new($false))
    Write-Host "Pinned FFmpeg release recorded in $PinFilePath : $TagName. Commit this file."
}

function Get-DigestSha256 {
    param(
        [Parameter(Mandatory = $false)]
        [string]$Digest
    )

    if ($Digest -and $Digest -match '^sha256:(?<value>[0-9a-fA-F]{64})$') {
        return $Matches.value.ToLowerInvariant()
    }
    return ""
}

function Get-ToolVersionLine {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ToolPath
    )

    if (-not (Test-Path -LiteralPath $ToolPath)) {
        throw "Binary not found: $ToolPath"
    }

    $output = & $ToolPath -version 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $output) {
        throw "Unable to read version from $ToolPath"
    }

    return [string]($output | Select-Object -First 1)
}

function Get-VersionToken {
    param(
        [Parameter(Mandatory = $true)]
        [string]$VersionLine
    )

    $match = [regex]::Match($VersionLine, 'version\s+(?<token>\S+)')
    if ($match.Success) {
        return $match.Groups['token'].Value
    }

    return ""
}

function Get-SemanticVersion {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    $match = [regex]::Match($Value, '^(?<version>\d+\.\d+(?:\.\d+)?)')
    if ($match.Success) {
        return $match.Groups['version'].Value
    }

    return ""
}

function ConvertTo-VersionTuple {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SemanticVersion
    )

    if (-not $SemanticVersion) {
        return $null
    }

    $parts = @($SemanticVersion.Split('.') | ForEach-Object { [int]$_ })
    while ($parts.Count -lt 3) {
        $parts += 0
    }

    return [int[]]$parts[0..2]
}

function Compare-VersionTuples {
    param(
        [Parameter(Mandatory = $true)]
        [int[]]$Left,
        [Parameter(Mandatory = $true)]
        [int[]]$Right
    )

    for ($index = 0; $index -lt 3; $index++) {
        if ($Left[$index] -gt $Right[$index]) {
            return 1
        }
        if ($Left[$index] -lt $Right[$index]) {
            return -1
        }
    }

    return 0
}

function Get-BuildDate {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    $match = [regex]::Match($Value, '^(?<date>\d{4}-\d{2}-\d{2})')
    if (-not $match.Success) {
        return $null
    }

    return [datetime]::ParseExact(
        $match.Groups['date'].Value,
        'yyyy-MM-dd',
        [System.Globalization.CultureInfo]::InvariantCulture
    ).Date
}

function Get-EmbeddedBinaryMetadata {
    param(
        [Parameter(Mandatory = $true)]
        [string]$VersionLine
    )

    $token = Get-VersionToken -VersionLine $VersionLine
    $semanticVersion = Get-SemanticVersion -Value $token
    $buildDate = Get-BuildDate -Value $token
    $semanticTuple = $null
    if ($semanticVersion) {
        $semanticTuple = ConvertTo-VersionTuple -SemanticVersion $semanticVersion
    }

    return [pscustomobject]@{
        VersionLine      = $VersionLine
        Token            = $token
        SemanticVersion  = $semanticVersion
        SemanticTuple    = $semanticTuple
        BuildDate        = $buildDate
    }
}

function Get-ReleaseMetadata {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Release
    )

    $tagName = [string]($Release.tag_name | ForEach-Object { $_ })
    $semanticVersion = Get-SemanticVersion -Value $tagName
    $publishedDate = $null
    $semanticTuple = $null

    if ($semanticVersion) {
        $semanticTuple = ConvertTo-VersionTuple -SemanticVersion $semanticVersion
    }

    if ($Release.published_at) {
        $publishedDate = ([datetime]$Release.published_at).Date
    }

    return [pscustomobject]@{
        TagName          = $tagName
        SemanticVersion  = $semanticVersion
        SemanticTuple    = $semanticTuple
        PublishedDate    = $publishedDate
        HtmlUrl          = [string]$Release.html_url
    }
}

function Get-UpdateDecision {
    param(
        [Parameter(Mandatory = $true)]
        [pscustomobject]$Current,
        [Parameter(Mandatory = $true)]
        [pscustomobject]$Latest
    )

    # The GyanD release tag (e.g. 2026-05-28-git-7b46c6a2a3) is the exact build
    # token, and the embedded ffmpeg -version line starts with that same token.
    # Comparing them directly is more reliable than date heuristics and needs no
    # download — so we can answer "already up to date" purely from API metadata.
    if ($Current.Token -and $Latest.TagName -and $Current.Token.StartsWith($Latest.TagName)) {
        return [pscustomobject]@{
            ShouldDownload = $false
            Reason = "Embedded FFmpeg already matches the latest GitHub release $($Latest.TagName)."
        }
    }

    if ($Current.SemanticTuple -and $Latest.SemanticTuple) {
        $semanticComparison = Compare-VersionTuples -Left $Current.SemanticTuple -Right $Latest.SemanticTuple
        if ($semanticComparison -gt 0) {
            return [pscustomobject]@{
                ShouldDownload = $false
                Reason = "Embedded FFmpeg semantic version $($Current.SemanticVersion) is newer than GitHub release $($Latest.SemanticVersion)."
            }
        }
        if ($semanticComparison -eq 0) {
            return [pscustomobject]@{
                ShouldDownload = $false
                Reason = "Embedded FFmpeg semantic version already matches GitHub release $($Latest.SemanticVersion)."
            }
        }
    }

    if ($Current.BuildDate -and $Latest.PublishedDate) {
        if ($Current.BuildDate -gt $Latest.PublishedDate) {
            return [pscustomobject]@{
                ShouldDownload = $false
                Reason = "Embedded FFmpeg build date $($Current.BuildDate.ToString('yyyy-MM-dd')) is newer than the latest GitHub release date $($Latest.PublishedDate.ToString('yyyy-MM-dd'))."
            }
        }
        if ($Current.BuildDate -eq $Latest.PublishedDate) {
            return [pscustomobject]@{
                ShouldDownload = $false
                Reason = "Embedded FFmpeg build date already matches the latest GitHub release date $($Latest.PublishedDate.ToString('yyyy-MM-dd'))."
            }
        }
    }

    return [pscustomobject]@{
        ShouldDownload = $true
        Reason = "A newer FFmpeg release may be available on GitHub."
    }
}

function Get-LatestReleaseWithEssentialsZip {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ApiUrl
    )

    try {
        $releases = Invoke-RestMethod -Uri $ApiUrl -Headers (Get-ApiHeaders)
    }
    catch {
        throw "Unable to fetch FFmpeg releases from GitHub API: $ApiUrl ($($_.Exception.Message))"
    }

    $release = $releases |
        Where-Object {
            @($_.assets) | Where-Object { $_.name -match '^ffmpeg-.*-essentials_build\.zip$' }
        } |
        Select-Object -First 1

    if ($release) {
        return $release
    }

    throw "Unable to find a published FFmpeg release with an essentials ZIP asset."
}

function Get-ReleaseByTag {
    param(
        [Parameter(Mandatory = $true)]
        [string]$TagName
    )

    if ($TagName -notmatch '^[0-9A-Za-z][0-9A-Za-z._-]*$') {
        throw "Invalid FFmpeg release tag: '$TagName'"
    }

    $url = $ReleaseByTagApiUrl + $TagName
    try {
        return Invoke-RestMethod -Uri $url -Headers (Get-ApiHeaders)
    }
    catch {
        throw "Unable to fetch FFmpeg release '$TagName' from GitHub API: $url ($($_.Exception.Message))"
    }
}

function Get-EssentialsZipAsset {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Release,
        [Parameter(Mandatory = $false)]
        [string]$ExactName
    )

    if ($ExactName) {
        $asset = @($Release.assets) | Where-Object { $_.name -eq $ExactName } | Select-Object -First 1
        if (-not $asset) {
            throw "Asset '$ExactName' not found in FFmpeg release $($Release.tag_name)."
        }
        return $asset
    }

    $asset = @($Release.assets) |
        Where-Object { $_.name -match '^ffmpeg-.*-essentials_build\.zip$' } |
        Select-Object -First 1

    if (-not $asset) {
        throw "Unable to find an essentials ZIP asset in the selected FFmpeg release."
    }

    return $asset
}

function Test-ArchiveDigest {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ArchivePath,
        [Parameter(Mandatory = $false)]
        [string]$Digest,
        [Parameter(Mandatory = $false)]
        [string]$PinnedSha256
    )

    $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ArchivePath).Hash.ToLowerInvariant()

    # Pinned mode: the hash committed in the repository is authoritative, whatever
    # GitHub reports today (an asset re-uploaded under the same tag must not slip in).
    if ($PinnedSha256) {
        $expectedPinned = $PinnedSha256.ToLowerInvariant()
        if ($actualHash -ne $expectedPinned) {
            throw "Downloaded archive does not match the pinned SHA256. Expected $expectedPinned (from $PinFilePath) but got $actualHash."
        }
        Write-Host "Archive SHA256 matches the pinned value: $actualHash"
    }

    if (-not $Digest) {
        if (-not $PinnedSha256) {
            Write-Warning "GitHub reported no digest for this asset; SHA256 not verified ($actualHash)."
        }
        return $actualHash
    }

    $expectedHash = Get-DigestSha256 -Digest $Digest
    if (-not $expectedHash) {
        Write-Warning "Unsupported digest format reported by GitHub: $Digest"
        return $actualHash
    }

    if ($actualHash -ne $expectedHash) {
        throw "Downloaded archive hash mismatch. Expected $expectedHash but got $actualHash."
    }

    return $actualHash
}

function Find-ExtractedBinary {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ExtractRoot,
        [Parameter(Mandatory = $true)]
        [string]$FileName
    )

    $matches = @(Get-ChildItem -Path $ExtractRoot -Recurse -File -Filter $FileName)
    if (-not $matches) {
        throw "Unable to find $FileName in the extracted archive."
    }

    $preferred = $matches | Where-Object { $_.DirectoryName -match '[\\/]bin$' } | Select-Object -First 1
    if ($preferred) {
        return $preferred.FullName
    }

    return $matches[0].FullName
}

function Restore-BinaryFromBackup {
    param(
        [Parameter(Mandatory = $true)]
        [string]$TargetPath,
        [Parameter(Mandatory = $true)]
        [string]$BackupPath,
        [Parameter(Mandatory = $true)]
        [bool]$PreviouslyExisted
    )

    if ($PreviouslyExisted -and (Test-Path -LiteralPath $BackupPath)) {
        Copy-Item -LiteralPath $BackupPath -Destination $TargetPath -Force
        return
    }

    if (-not $PreviouslyExisted -and (Test-Path -LiteralPath $TargetPath)) {
        Remove-Item -LiteralPath $TargetPath -Force
    }
}

function Invoke-WithoutWhatIf {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$ScriptBlock
    )

    $previousWhatIfPreference = $WhatIfPreference
    try {
        $WhatIfPreference = $false
        & $ScriptBlock
    }
    finally {
        $WhatIfPreference = $previousWhatIfPreference
    }
}

# bin/ is not git-tracked (GyanD builds exceed GitHub's 100 MB file limit since
# 9.0.2): on a fresh clone the binaries are absent, and this script installs them.
$hasEmbeddedBinaries = (Test-Path -LiteralPath $FfmpegPath) -and (Test-Path -LiteralPath $FfprobePath)
$currentFfmpegVersion = $null
$currentFfprobeVersion = $null
$currentMetadata = $null

if ($hasEmbeddedBinaries) {
    $currentFfmpegVersion = Get-ToolVersionLine -ToolPath $FfmpegPath
    $currentFfprobeVersion = Get-ToolVersionLine -ToolPath $FfprobePath
    $currentMetadata = Get-EmbeddedBinaryMetadata -VersionLine $currentFfmpegVersion

    Write-Host "Current embedded FFmpeg : $currentFfmpegVersion"
    Write-Host "Current embedded FFprobe: $currentFfprobeVersion"
    if ($currentMetadata.SemanticVersion) {
        Write-Host "Current semantic version: $($currentMetadata.SemanticVersion)"
    }
    if ($currentMetadata.BuildDate) {
        Write-Host "Current build date      : $($currentMetadata.BuildDate.ToString('yyyy-MM-dd'))"
    }
}
else {
    Write-Host "No embedded FFmpeg in $BinDir (fresh clone?): the selected release will be installed."
}

$pinnedSha256 = ""
if ($Pinned) {
    $pin = Read-PinFile
    $pinnedSha256 = [string]$pin.sha256
    Write-Host "Pinned release (from $PinFilePath): $($pin.tag)"
    $release = Get-ReleaseByTag -TagName ([string]$pin.tag)
    $asset = Get-EssentialsZipAsset -Release $release -ExactName ([string]$pin.asset)
}
elseif ($Tag) {
    $release = Get-ReleaseByTag -TagName $Tag
    $asset = Get-EssentialsZipAsset -Release $release
}
else {
    $release = Get-LatestReleaseWithEssentialsZip -ApiUrl $ReleasesApiUrl
    $asset = Get-EssentialsZipAsset -Release $release
}
$releaseMetadata = Get-ReleaseMetadata -Release $release

Write-Host "Selected GitHub release: $($release.tag_name)"
Write-Host "Selected asset         : $($asset.name)"
if ($releaseMetadata.SemanticVersion) {
    Write-Host "Release semantic version: $($releaseMetadata.SemanticVersion)"
}
if ($releaseMetadata.PublishedDate) {
    Write-Host "Release date            : $($releaseMetadata.PublishedDate.ToString('yyyy-MM-dd'))"
}

# The embedded ffmpeg -version token starts with the exact GyanD tag
# (9.0.2-essentials_build-www.gyan.dev for tag 9.0.2).
$embeddedMatchesRelease = $hasEmbeddedBinaries -and $currentMetadata.Token -and (
    $currentMetadata.Token -eq $release.tag_name -or
    $currentMetadata.Token.StartsWith("$($release.tag_name)-")
)

if ($Pinned -or $Tag) {
    # An explicit release is installed as is, older or newer: no date or version
    # heuristics, only "is it already the one in bin\?".
    if ($embeddedMatchesRelease) {
        $decision = [pscustomobject]@{
            ShouldDownload = $false
            Reason = "Embedded FFmpeg already matches the requested release $($release.tag_name)."
        }
    }
    else {
        $decision = [pscustomobject]@{
            ShouldDownload = $true
            Reason = "Installing the requested GitHub release $($release.tag_name)."
        }
    }
}
elseif ($hasEmbeddedBinaries) {
    $decision = Get-UpdateDecision -Current $currentMetadata -Latest $releaseMetadata
}
else {
    $decision = [pscustomobject]@{
        ShouldDownload = $true
        Reason = "Embedded FFmpeg is missing; installing GitHub release $($release.tag_name)."
    }
}
Write-Host $decision.Reason

if (-not $decision.ShouldDownload) {
    # Keep the pin in step with what bin\ really holds (e.g. the first run after the
    # pin file was introduced). Never in -Pinned mode: there the file is the input.
    if (-not $Pinned -and -not $CheckOnly -and $embeddedMatchesRelease) {
        $digestSha256 = ""
        if ($asset.PSObject.Properties.Name -contains "digest") {
            $digestSha256 = Get-DigestSha256 -Digest ([string]$asset.digest)
        }
        if ($digestSha256) {
            Write-PinFile -TagName $release.tag_name -AssetName $asset.name -Sha256 $digestSha256
        }
        else {
            Write-Warning "GitHub reported no SHA256 for $($asset.name); pin file left unchanged."
        }
    }
    return
}

# A dry run only needs to know whether an update exists. The release tag already
# tells us that, so report it and stop before downloading the ~115 MB archive.
if ($CheckOnly) {
    Write-Host "An embedded FFmpeg update is available: $($release.tag_name)"
    Write-Host "Run without -CheckOnly to download, verify, and install it."
    Write-Host "Release page: $($release.html_url)"
    return
}

$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("amc-ffmpeg-update-" + [Guid]::NewGuid().ToString("N"))
$downloadPath = Join-Path $tempRoot $asset.name
$extractRoot = Join-Path $tempRoot "extract"
$backupRoot = Join-Path $tempRoot "backup"

[void][System.IO.Directory]::CreateDirectory($tempRoot)
[void][System.IO.Directory]::CreateDirectory($extractRoot)
[void][System.IO.Directory]::CreateDirectory($backupRoot)

try {
    Write-Host "Downloading essentials archive $($asset.name)..."
    Invoke-WithoutWhatIf {
        Invoke-WebRequest -Uri $asset.browser_download_url -Headers @{
            "Accept"     = "application/octet-stream"
            "User-Agent" = $UserAgent
        } -OutFile $downloadPath -UseBasicParsing
    }

    $assetDigest = ""
    if ($asset.PSObject.Properties.Name -contains "digest") {
        $assetDigest = [string]$asset.digest
    }
    $archiveSha256 = Test-ArchiveDigest -ArchivePath $downloadPath -Digest $assetDigest -PinnedSha256 $pinnedSha256

    Write-Host "Extracting archive..."
    Invoke-WithoutWhatIf {
        Expand-Archive -LiteralPath $downloadPath -DestinationPath $extractRoot -Force
    }

    $candidateFfmpegPath = Find-ExtractedBinary -ExtractRoot $extractRoot -FileName "ffmpeg.exe"
    $candidateFfprobePath = Find-ExtractedBinary -ExtractRoot $extractRoot -FileName "ffprobe.exe"

    $candidateFfmpegVersion = Get-ToolVersionLine -ToolPath $candidateFfmpegPath
    $candidateFfprobeVersion = Get-ToolVersionLine -ToolPath $candidateFfprobePath

    Write-Host "Candidate FFmpeg    : $candidateFfmpegVersion"
    Write-Host "Candidate FFprobe   : $candidateFfprobeVersion"

    if ($candidateFfmpegVersion -eq $currentFfmpegVersion -and $candidateFfprobeVersion -eq $currentFfprobeVersion) {
        if (-not $Pinned) {
            Write-PinFile -TagName $release.tag_name -AssetName $asset.name -Sha256 $archiveSha256
        }
        Write-Host "Embedded FFmpeg binaries are already up to date."
        return
    }

    New-Item -ItemType Directory -Path $BinDir -Force | Out-Null

    $backupFfmpegPath = Join-Path $backupRoot "ffmpeg.exe"
    $backupFfprobePath = Join-Path $backupRoot "ffprobe.exe"
    $hadFfmpeg = Test-Path -LiteralPath $FfmpegPath
    $hadFfprobe = Test-Path -LiteralPath $FfprobePath

    if ($hadFfmpeg) {
        Copy-Item -LiteralPath $FfmpegPath -Destination $backupFfmpegPath -Force
    }
    if ($hadFfprobe) {
        Copy-Item -LiteralPath $FfprobePath -Destination $backupFfprobePath -Force
    }

    if ($PSCmdlet.ShouldProcess($BinDir, "Replace embedded FFmpeg binaries from release $($release.tag_name)")) {
        try {
            Copy-Item -LiteralPath $candidateFfmpegPath -Destination $FfmpegPath -Force
            Copy-Item -LiteralPath $candidateFfprobePath -Destination $FfprobePath -Force

            $installedFfmpegVersion = Get-ToolVersionLine -ToolPath $FfmpegPath
            $installedFfprobeVersion = Get-ToolVersionLine -ToolPath $FfprobePath

            if ($installedFfmpegVersion -ne $candidateFfmpegVersion) {
                throw "Installed ffmpeg.exe version does not match the downloaded candidate."
            }
            if ($installedFfprobeVersion -ne $candidateFfprobeVersion) {
                throw "Installed ffprobe.exe version does not match the downloaded candidate."
            }

            if (-not $Pinned) {
                Write-PinFile -TagName $release.tag_name -AssetName $asset.name -Sha256 $archiveSha256
            }
            Write-Host "Embedded FFmpeg binaries updated successfully."
            Write-Host "Release page: $($release.html_url)"
        }
        catch {
            Restore-BinaryFromBackup -TargetPath $FfmpegPath -BackupPath $backupFfmpegPath -PreviouslyExisted $hadFfmpeg
            Restore-BinaryFromBackup -TargetPath $FfprobePath -BackupPath $backupFfprobePath -PreviouslyExisted $hadFfprobe
            throw
        }
    }
}
finally {
    if (Test-Path -LiteralPath $tempRoot) {
        Invoke-WithoutWhatIf {
            Remove-Item -LiteralPath $tempRoot -Recurse -Force
        }
    }
}
