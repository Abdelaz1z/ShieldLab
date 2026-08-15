$ErrorActionPreference = 'Stop'
$repo = 'D:\Projects\Master\Master-26\Control Claude Program'
$backup = Join-Path $repo '_backups\lead_subthreshold_result_integration_20260815'
$utf8 = New-Object System.Text.UTF8Encoding($false)
New-Item -ItemType Directory -Force -Path $backup | Out-Null

function Replace-Once([string]$Text, [string]$Old, [string]$New, [string]$Label) {
    if ([regex]::Matches($Text, [regex]::Escape($Old)).Count -ne 1) { throw "$Label preimage not unique" }
    return $Text.Replace($Old, $New)
}

function Publish([string]$Path, [string]$Text, [string]$BackupName) {
    $staged = "$Path.replacement"
    [IO.File]::WriteAllText($staged, $Text, $utf8)
    Copy-Item -LiteralPath $Path -Destination (Join-Path $backup $BackupName)
    Move-Item -LiteralPath $Path -Destination (Join-Path $backup "original_$BackupName")
    Move-Item -LiteralPath $staged -Destination $Path
}

$enginePath = Join-Path $repo 'shieldlab\room\engines.py'
$engine = [IO.File]::ReadAllText($enginePath, [Text.Encoding]::UTF8)
$nl = if ($engine.Contains("`r`n")) { "`r`n" } else { "`n" }
$oldComment = @(
    '# not thereby validated: every surrogate label remains a finite-field quantity until a wider-field',
    '# corpus is generated.'
) -join $nl
$newComment = @(
    '# not thereby validated: every surrogate label remains a finite-field quantity until a wider-field',
    '# corpus is generated.',
    '#',
    '# A later prospective pure-lead study at 511 and 364 keV completed all 13 fixed-budget rows, but',
    '# eight missed its preregistered 0.8% precision gate. Its official decision did not constrain the',
    '# 0.5-to-2.0 m field-width change below 10%, so it does not justify weakening this warning.'
) -join $nl
$engine = Replace-Once $engine $oldComment $newComment 'engine comment'
$engineWarning = @(
    '    "still rising. A fixed-budget pure-lead study at 511 and 364 keV failed its "',
    '    "precision gate and did not constrain the field-width effect below 10%; lead "',
    '    "and other material/energy cases remain decision-unquantified. An independent "'
) -join $nl
$engine = Replace-Once $engine '    "still rising; other materials and energies are unquantified. An independent "' $engineWarning 'engine warning'

$reportPath = Join-Path $repo 'shieldlab\room\report_regulatory.py'
$report = [IO.File]::ReadAllText($reportPath, [Text.Encoding]::UTF8)
$reportNl = if ($report.Contains("`r`n")) { "`r`n" } else { "`n" }
$oldReport = @(
    '        "broad beam. The bias magnitude has been measured only for concrete at 364&nbsp;keV. "',
    '        "It was already present at the shallowest tested depth (&mu;x&nbsp;&asymp;&nbsp;4), so "',
    '        "no lower bound on its physical onset has been established; behaviour for lead and "',
    '        "other materials or energies is unquantified. The &mu;x&ge;4 red flag is a priority "'
) -join $reportNl
$newReport = @(
    '        "broad beam. A decision-qualified bias magnitude has been established only for concrete "',
    '        "at 364&nbsp;keV. A prospective fixed-budget pure-lead study at 511 and 364&nbsp;keV "',
    '        "failed its preregistered precision gate and did not constrain the 0.5-to-2.0&nbsp;m "',
    '        "field-width effect below 10%; lead therefore remains decision-unquantified. "',
    '        "It was already present at the shallowest tested depth (&mu;x&nbsp;&asymp;&nbsp;4), so "',
    '        "no lower bound on its physical onset has been established; other materials or energies "',
    '        "remain unquantified. The &mu;x&ge;4 red flag is a priority "'
) -join $reportNl
$report = Replace-Once $report $oldReport $newReport 'regulatory scope'

$testPath = Join-Path $repo 'tests\test_room_surrogate.py'
$test = [IO.File]::ReadAllText($testPath, [Text.Encoding]::UTF8)
$testNl = if ($test.Contains("`r`n")) { "`r`n" } else { "`n" }
$test = Replace-Once $test '        "lower bounds", "Monte-Carlo",' '        "lower bounds", "precision gate", "below 10%", "Monte-Carlo",' 'warning assertions'
$reportAssertions = @(
    '    assert "lead" in document',
    '    assert "precision gate" in document',
    '    assert "below 10%" in document'
) -join $testNl
$test = Replace-Once $test '    assert "lead" in document' $reportAssertions 'report assertions'

Publish $enginePath $engine 'engines.py'
Publish $reportPath $report 'report_regulatory.py'
Publish $testPath $test 'test_room_surrogate.py'
Write-Output 'LEAD_RESULT_WARNING_PATCH_PASS'
