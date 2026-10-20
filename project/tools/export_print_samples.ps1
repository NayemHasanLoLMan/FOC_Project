# Legacy test-tool entry point; implementation lives in tests/evaluation.
param(
    [Parameter(Mandatory = $true)][string[]]$Invoices,
    [string]$OutputDir = (Join-Path $PSScriptRoot '../reports/print_check')
)
& (Join-Path $PSScriptRoot '../tests/evaluation/export_print_samples.ps1') -Invoices $Invoices -OutputDir $OutputDir
