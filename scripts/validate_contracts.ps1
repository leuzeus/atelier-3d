param([string]$OfficialSchemaDirectory)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$checks = [Collections.Generic.List[object]]::new()
function Test-Contract([string]$Instance, [string]$Schema) {
    $valid = Get-Content -LiteralPath $Instance -Raw | Test-Json -SchemaFile $Schema
    if (-not $valid) { throw "Contract validation failed: $Instance" }
    $checks.Add([pscustomobject]@{ file = [IO.Path]::GetRelativePath($projectRoot, $Instance); result = 'PASS' })
}
Test-Contract (Join-Path $projectRoot 'templates/config.json') (Join-Path $projectRoot 'schemas/config.schema.json')
$localConfig = Join-Path $projectRoot 'config.local.json'
if (Test-Path -LiteralPath $localConfig) {
    Test-Contract $localConfig (Join-Path $projectRoot 'schemas/config.schema.json')
}
Get-ChildItem -LiteralPath (Join-Path $projectRoot 'tests/fixtures') -Recurse -Filter '*.json' | ForEach-Object {
    $schemaName = switch ($_.Name) {
        'asset.json' { 'asset' }
        'garment.json' { 'garment' }
        'part.json' { 'part-package' }
        default { throw "Unmapped fixture: $($_.FullName)" }
    }
    Test-Contract $_.FullName (Join-Path $projectRoot "schemas/$schemaName.schema.json")
}
if ($OfficialSchemaDirectory) {
    Test-Contract (Join-Path $projectRoot 'plugin.json') (Join-Path $OfficialSchemaDirectory 'plugin.schema.json')
    Test-Contract (Join-Path $projectRoot 'mcp.json') (Join-Path $OfficialSchemaDirectory 'mcp.schema.json')
}
[pscustomobject]@{ validator='PowerShell Test-Json'; passed=$checks.Count; checks=$checks } | ConvertTo-Json -Depth 5
