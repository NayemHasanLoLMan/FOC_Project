param(
    [Parameter(Mandatory = $true)][string[]]$Invoices,
    [string]$OutputDir = (Join-Path $PSScriptRoot '../reports/print_check')
)
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$excelApp = New-Object -ComObject Excel.Application
$excelApp.Visible = $false
$excelApp.DisplayAlerts = $false
$excelApp.AutomationSecurity = 3
try {
    foreach ($invoice in $Invoices) {
        $bookPath = (Resolve-Path -LiteralPath $invoice).Path
        $pdfPath = [IO.Path]::GetFullPath((Join-Path $OutputDir ([IO.Path]::GetFileNameWithoutExtension($bookPath) + '.pdf')))
        $book = $excelApp.Workbooks.Open($bookPath, 0, $true)
        try {
            $book.Worksheets.Item(1).ExportAsFixedFormat(0, $pdfPath)
            Write-Output "Exported $pdfPath"
        } finally {
            $book.Close($false)
            [void][Runtime.InteropServices.Marshal]::ReleaseComObject($book)
        }
    }
} finally {
    $excelApp.Quit()
    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($excelApp)
}
