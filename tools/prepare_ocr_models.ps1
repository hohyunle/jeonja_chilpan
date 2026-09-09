param(
    [string]$SourceRoot = (Join-Path ([Environment]::GetFolderPath('UserProfile')) '.paddlex\official_models'),
    [string]$DestinationRoot = 'C:\Temp\CodeTrace\models'
)

$modelNames = @(
    'PP-OCRv5_mobile_det',
    'korean_PP-OCRv5_mobile_rec'
)

New-Item -ItemType Directory -Force -Path $DestinationRoot | Out-Null

foreach ($modelName in $modelNames) {
    $sourcePath = Join-Path $SourceRoot $modelName
    $destinationPath = Join-Path $DestinationRoot $modelName
    if (-not (Test-Path -LiteralPath $sourcePath -PathType Container)) {
        throw "OCR model directory was not found: $sourcePath"
    }
    Copy-Item -LiteralPath $sourcePath -Destination $destinationPath -Recurse -Force
}

Write-Output "Offline OCR models copied to $DestinationRoot"
