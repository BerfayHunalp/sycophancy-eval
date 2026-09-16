# Full run, detached from any terminal session. Usage (from the repo root):
#   powershell -ExecutionPolicy Bypass -File scripts/run_full.ps1 -Rpm 18
# Order: core personas (H1/H3a/H4) -> Conscientiousness personas -> IPIP manipulation check.
# Each stage resumes from results/*.jsonl, so re-running the script after a crash is safe.
# Log: results/run-01.log. Progress bars are throttled to one line per 30 s.
param(
    [double]$Rpm = 18,
    [int]$Concurrency = 4
)
$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..")
$env:TQDM_MININTERVAL = "30"
$env:PYTHONIOENCODING = "utf-8"
$log = "results/run-01.log"

function Stage([string]$name, [string[]]$cmdArgs) {
    "=== $name  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Tee-Object -FilePath $log -Append
    & py @cmdArgs 2>&1 | Tee-Object -FilePath $log -Append
    if ($LASTEXITCODE -ne 0) {
        "=== $name FAILED (exit $LASTEXITCODE)  $(Get-Date -Format 'HH:mm:ss') ===" | Tee-Object -FilePath $log -Append
        exit $LASTEXITCODE
    }
}

Stage "study core personas" @("scripts/run_study.py", "--personas", "none", "high_A", "low_A",
                              "--rpm", "$Rpm", "--concurrency", "$Concurrency")
Stage "study C personas"    @("scripts/run_study.py", "--personas", "high_C", "low_C",
                              "--rpm", "$Rpm", "--concurrency", "$Concurrency")
Stage "ipip check"          @("scripts/run_ipip.py", "--rpm", "$Rpm", "--concurrency", "$Concurrency")
"=== ALL STAGES DONE  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Tee-Object -FilePath $log -Append
