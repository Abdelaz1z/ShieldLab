$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$sourcePath = Join-Path $root '_fix_beamwidth_warning_review_20260814.ps1'
$utf8 = [Text.UTF8Encoding]::new($false)
$source = [IO.File]::ReadAllText($sourcePath, $utf8)
$source = $source.Replace('$Label:', '${Label}:').Replace('$RelativePath:', '${RelativePath}:')
$tokens = $null
$errors = $null
$ast = [Management.Automation.Language.Parser]::ParseInput($source, [ref]$tokens, [ref]$errors)
if ($errors.Count) { $errors | ForEach-Object { Write-Error $_.Message }; exit 1 }
Invoke-Expression $source
