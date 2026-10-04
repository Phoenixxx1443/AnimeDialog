param([string]$InputDocx,[string]$OutputPdf)
$adDocxPath=(Resolve-Path -LiteralPath $InputDocx).Path
$adPdfPath=[System.IO.Path]::GetFullPath($OutputPdf)
$adWord=New-Object -ComObject Word.Application
$adWord.Visible=$false
$adWord.DisplayAlerts=0
try {
    $adDocument=$adWord.Documents.Open($adDocxPath,$false,$true)
    $adDocument.ExportAsFixedFormat($adPdfPath,17)
    $adDocument.Close($false)
    Write-Output $adPdfPath
} finally {
    $adWord.Quit()
    [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($adWord) | Out-Null
}
