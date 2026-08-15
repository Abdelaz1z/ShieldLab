$ErrorActionPreference = 'Stop'
$utf8 = [Text.UTF8Encoding]::new($false)
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backup = Join-Path $root '_backups\beamwidth2_warning_review_20260814'
[IO.Directory]::CreateDirectory($backup) | Out-Null

function Replace-Once([string]$Text, [string]$Old, [string]$New, [string]$Label) {
    $first = $Text.IndexOf($Old, [StringComparison]::Ordinal)
    if ($first -lt 0) { throw "$Label: old text not found" }
    if ($Text.IndexOf($Old, $first + $Old.Length, [StringComparison]::Ordinal) -ge 0) {
        throw "$Label: old text is not unique"
    }
    return $Text.Substring(0, $first) + $New + $Text.Substring($first + $Old.Length)
}

function Update-File([string]$RelativePath, [scriptblock]$Transform) {
    $path = Join-Path $root $RelativePath
    Copy-Item -LiteralPath $path -Destination (Join-Path $backup ($RelativePath -replace '[\\/]', '__')) -Force
    $old = [IO.File]::ReadAllText($path, $utf8)
    $new = & $Transform $old
    if ($new -ceq $old) { throw "$RelativePath: no change" }
    $stage = "$path.stage"
    [IO.File]::WriteAllText($stage, $new, $utf8)
    Move-Item -LiteralPath $stage -Destination $path -Force
}

Update-File 'shieldlab\room\engines.py' {
    param($text)
    $text = Replace-Once $text @'
# Every training label used a finite 0.5 m square beam. The locked Beamwidth-2 study measured
# resolved increases already at concrete/364 keV mu*x=3.97 and 5.95: widening 0.5 -> 1.0 m
'@ @'
# Every training label used a finite 0.5 m square beam. The locked Beamwidth-2 study measured
# resolved increases at every tested optical depth. Its shallowest points were concrete/364 keV
# mu*x=3.97 and 5.95: widening 0.5 -> 1.0 m
'@ 'engine measured-depth comment'
    $text = Replace-Once $text @'
# The magnitude is measured only for solid concrete at 364 keV. Applying the warning to all
# materials/energies is a conservative routing policy, not a claim that they share one correction
# factor. The labels remain finite-field quantities until a wider-field corpus is generated.
'@ @'
# The magnitude is measured only for solid concrete at 364 keV. Because the bias was already 1.58x
# at the shallowest tested depth, the physical onset is unknown and may be below mu*x=3.97. The
# mu*x>=4 red flag is a priority rule, not an onset claim. Materials/energies without red flags are
# not thereby validated: every surrogate label remains a finite-field quantity until a wider-field
# corpus is generated.
'@ 'engine scope comment'
    $text = Replace-Once $text @'
GEOMETRY_BIAS_WARNING = (
    "Caution: Finite-beam transmission (μx≥4) carries an uncorrected geometry bias "
    "(under-prediction of scatter). This onset was measured for concrete at 364 keV; "
    "the magnitude at other materials and energies is unquantified. An independent "
    "Monte-Carlo check with reviewed irradiation geometry is required for final design sign-off."
)
'@ @'
GEOMETRY_BIAS_WARNING = (
    "Caution: Finite-beam transmission (μx≥4) carries an uncorrected geometry bias "
    "(under-prediction of scatter). Bias was measured at every optical depth tested "
    "(μx≈4–12, concrete at 364 keV): 1.58× to 2.0×. It was already 1.58× at the "
    "shallowest depth measured, so no lower bound on its onset has been established. "
    "The measured factors are lower bounds because the shallow width sequences were "
    "still rising; other materials and energies are unquantified. An independent "
    "Monte-Carlo check with reviewed irradiation geometry is required for final design sign-off."
)
'@ 'engine warning'
    return $text
}

Update-File 'shieldlab\room\report_regulatory.py' {
    param($text)
    $text = Replace-Once $text @'
            f"study measured 0.5&nbsp;m to 1.5&nbsp;m increases of 1.58&times; and 1.73&times; at "
            f"&mu;x&nbsp;4 and 6 in concrete at 364&nbsp;keV; historical deep rows increased "
            f"1.8–2.0&times; at &mu;x&nbsp;8–12. The surrogate may therefore report transmission "
'@ @'
            f"study measured 0.5&nbsp;m to 1.5&nbsp;m increases of 1.58&times; and 1.73&times; at "
            f"&mu;x&nbsp;4 and 6 in concrete at 364&nbsp;keV; historical deep rows increased "
            f"1.8–2.0&times; at &mu;x&nbsp;8–12. These are lower bounds: the final "
            f"1.0&nbsp;m to 1.5&nbsp;m steps still added 9.3% and 9.8% at more than four "
            f"combined standard deviations. The surrogate may therefore report transmission "
'@ 'regulatory lower-bound disclosure'
    $text = Replace-Once $text @'
            f"</div>")

    findings = report.get("failure_explanations") or []
'@ @'
            f"</div>")

    finite_field_scope_html = (
        "<div class='band'><b>Model-wide finite-field scope.</b> Every Monte-Carlo surrogate "
        "result is calibrated to a finite 0.5&nbsp;m irradiated field, not a semi-infinite "
        "broad beam. The bias magnitude has been measured only for concrete at 364&nbsp;keV. "
        "It was already present at the shallowest tested depth (&mu;x&nbsp;&asymp;&nbsp;4), so "
        "no lower bound on its physical onset has been established; behaviour for lead and "
        "other materials or energies is unquantified. The &mu;x&ge;4 red flag is a priority "
        "classification, not evidence that unflagged surrogate results are free of finite-field bias."
        "</div>"
    )

    findings = report.get("failure_explanations") or []
'@ 'regulatory model-wide scope'
    $text = Replace-Once $text @'
<p>{_esc(report.get('disclaimer'))}</p>
{geometry_bias_html}
'@ @'
<p>{_esc(report.get('disclaimer'))}</p>
{finite_field_scope_html}
{geometry_bias_html}
'@ 'regulatory section-eight insertion'
    return $text
}

Update-File 'ui\i18n.py' {
    param($text)
    $text = Replace-Once $text @'
    "finite_beam_warning": "**Potential finite-beam underprediction.** The surrogate may read low from μx≥4 — the unsafe direction. Treat these paths as **Review Required** and confirm them with reviewed Monte-Carlo irradiation geometry.\n\n{paths}",
'@ @'
    "finite_beam_warning": "**Potential finite-beam underprediction — priority flag.** These μx≥4 paths fall inside the measured-risk region and may read low, the unsafe direction. The threshold is not a measured onset; all surrogate results remain finite-field quantities. Treat these paths as **Review Required** and confirm them with reviewed Monte-Carlo irradiation geometry.\n\n{paths}",
'@ 'English UI warning'
    $text = Replace-Once $text @'
    "finite_beam_warning": "**احتمال تقليل الجرعة بسبب الحزمة المحدودة.** قد يقرأ النموذج البديل قيمة منخفضة ابتداءً من μx≥4، وهو الاتجاه غير الآمن. اعتبر هذه المسارات **بحاجة إلى مراجعة** وأكّدها بمونت كارلو باستخدام هندسة تشعيع مُراجعة.\n\n{paths}",
'@ @'
    "finite_beam_warning": "**احتمال تقليل الجرعة بسبب الحزمة المحدودة — تحذير أولوية.** تقع مسارات μx≥4 داخل النطاق الذي قيس فيه الخطر وقد تقرأ قيمة منخفضة، وهو الاتجاه غير الآمن. العتبة ليست بداية فيزيائية مقاسة؛ كل نتائج النموذج تظل كميات لحزمة محدودة. اعتبر هذه المسارات **بحاجة إلى مراجعة** وأكّدها بمونت كارلو باستخدام هندسة تشعيع مُراجعة.\n\n{paths}",
'@ 'Arabic UI warning'
    return $text
}

Update-File 'tests\test_room_surrogate.py' {
    param($text)
    $text = Replace-Once $text 'def test_2026_08_14_finite_beam_geometry_warning_starts_at_mux4():' 'def test_2026_08_14_finite_beam_priority_warning_at_mux4():' 'test name'
    $text = Replace-Once $text '    """The measured shallow onset must reach both surrogate branches and signed reports."""' '    """The mu*x>=4 priority policy must not be presented as a measured physical onset."""' 'test docstring'
    $text = Replace-Once $text @'
    below_onset = _both(_room(iso="F-18", thickness=100))[2]["Wall N"]
    assert below_onset.mu_x is not None and below_onset.mu_x < eng.GEOMETRY_BIAS_MUX
    assert below_onset.geometry_bias is False
    assert eng.GEOMETRY_BIAS_WARNING not in below_onset.note

    measured_onset = _both(_room(iso="F-18", thickness=200))[2]["Wall N"]
    assert measured_onset.mu_x >= eng.GEOMETRY_BIAS_MUX
    assert measured_onset.geometry_bias is True
    assert eng.GEOMETRY_BIAS_WARNING in measured_onset.note
'@ @'
    below_priority_threshold = _both(_room(iso="F-18", thickness=100))[2]["Wall N"]
    assert below_priority_threshold.mu_x is not None
    assert below_priority_threshold.mu_x < eng.GEOMETRY_BIAS_MUX
    assert below_priority_threshold.geometry_bias is False
    assert eng.GEOMETRY_BIAS_WARNING not in below_priority_threshold.note

    priority_flagged = _both(_room(iso="F-18", thickness=200))[2]["Wall N"]
    assert priority_flagged.mu_x >= eng.GEOMETRY_BIAS_MUX
    assert priority_flagged.geometry_bias is True
    assert eng.GEOMETRY_BIAS_WARNING in priority_flagged.note
'@ 'test threshold variables'
    $text = Replace-Once $text @'
    for phrase in ("μx≥4", "geometry bias", "under-prediction of scatter", "Monte-Carlo"):
        assert phrase in warning, phrase
'@ @'
    for phrase in (
        "μx≥4", "geometry bias", "no lower bound on its onset",
        "lower bounds", "Monte-Carlo",
    ):
        assert phrase in warning, phrase
'@ 'test warning contract'
    $text = Replace-Once $text @'
    assert "Finite-beam caution" in document
    assert "Wall N" in document.split("Finite-beam caution")[1][:200]
'@ @'
    assert "Finite-beam caution" in document
    assert "Wall N" in document.split("Finite-beam caution")[1][:200]
    assert "lower bounds" in document
    assert "9.3% and 9.8%" in document
'@ 'test signed row caution'
    $text = Replace-Once $text @'
    assert "Finite-beam caution" not in \
           report_regulatory.build_submission_html(report, metadata).decode("utf-8")
'@ @'
    document = report_regulatory.build_submission_html(report, metadata).decode("utf-8")
    assert "Finite-beam caution" not in document
    assert "Model-wide finite-field scope" in document
    assert "no lower bound on its physical onset" in document
    assert "lead" in document
'@ 'test permanent signed scope'
    return $text
}

Get-FileHash -Algorithm SHA256 -LiteralPath @(
    (Join-Path $root 'shieldlab\room\engines.py'),
    (Join-Path $root 'shieldlab\room\report_regulatory.py'),
    (Join-Path $root 'ui\i18n.py'),
    (Join-Path $root 'tests\test_room_surrogate.py')
) | ForEach-Object { "$($_.Hash.ToLower())  $($_.Path)" }
