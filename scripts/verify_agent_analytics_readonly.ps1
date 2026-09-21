[CmdletBinding()]
param(
    [string]$Image = 'postgres:17@sha256:f4c66b820c6f974249089d3d16d86a3698eae11e8746eb6644b2271031e91232',
    [string]$CatalogPath = 'backend/app/query_analytics_catalog_v1.json',
    [switch]$KeepContainer
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$catalogFile = Join-Path $repoRoot $CatalogPath
$schemaFile = Join-Path $repoRoot 'backend/sql/008_fresh_handoff_schema.sql'
$migrationFile = Join-Path $repoRoot 'backend/sql/013_agent_analytics_readonly.sql'
$container = 'hormuz-sql02-' + $PID + '-' + (Get-Random -Minimum 1000 -Maximum 9999)
$database = 'hormuz_sql02_verify'
$admin = 'sql02_admin'
$adminPassword = [guid]::NewGuid().ToString('N')
$checks = [System.Collections.Generic.List[string]]::new()

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw "FAIL: $Message" }
    $script:checks.Add($Message)
}

function Invoke-Psql([string]$Role, [string]$Sql) {
    $output = & docker exec $container psql -X -v ON_ERROR_STOP=1 -U $Role -d $database -At -F "`t" -c $Sql 2>&1
    [pscustomobject]@{ ExitCode = $LASTEXITCODE; Output = @($output) }
}

function Assert-PsqlSuccess([string]$Role, [string]$Sql, [string]$Message) {
    $result = Invoke-Psql $Role $Sql
    if ($result.ExitCode -ne 0) { throw "FAIL: $Message`n$($result.Output -join [Environment]::NewLine)" }
    $script:checks.Add($Message)
    $result.Output
}

function Assert-PsqlDenied([string]$Sql, [string]$Message) {
    $result = Invoke-Psql 'agent_reader_login' $Sql
    if ($result.ExitCode -eq 0) { throw "FAIL: $Message unexpectedly succeeded" }
    $script:checks.Add($Message)
}

function Get-ViewHash([string]$ViewName) {
    $encoded = Assert-PsqlSuccess $admin "SELECT encode(convert_to(pg_get_viewdef('$ViewName'::regclass, false), 'UTF8'), 'base64');" "read normalized definition for $ViewName"
    $bytes = [Convert]::FromBase64String((($encoded -join '') -replace '\s', ''))
    $sha = [Security.Cryptography.SHA256]::Create()
    try { ([Convert]::ToHexString($sha.ComputeHash($bytes))).ToLowerInvariant() }
    finally { $sha.Dispose() }
}

function Compare-Catalog($Catalog) {
    $errors = [System.Collections.Generic.List[string]]::new()
    foreach ($view in $Catalog.views) {
        $ownerResult = Invoke-Psql $admin "SELECT pg_get_userbyid(c.relowner) FROM pg_class c WHERE c.oid = '$($view.name)'::regclass;"
        if ($ownerResult.ExitCode -ne 0 -or ($ownerResult.Output -join '').Trim() -ne $view.owner) {
            $errors.Add("$($view.name): owner mismatch")
        }

        $actualHash = Get-ViewHash $view.name
        if ($actualHash -ne $view.definition_sha256) {
            $errors.Add("$($view.name): definition hash expected=$($view.definition_sha256) actual=$actualHash")
        }

        $columnSql = @"
SELECT a.attname,
       format_type(a.atttypid, a.atttypmod),
       CASE WHEN i.is_nullable = 'YES' THEN 'true' ELSE 'false' END
FROM pg_attribute AS a
JOIN pg_class AS c ON c.oid = a.attrelid
JOIN pg_namespace AS n ON n.oid = c.relnamespace
JOIN information_schema.columns AS i
  ON i.table_schema = n.nspname
 AND i.table_name = c.relname
 AND i.column_name = a.attname
WHERE n.nspname = split_part('$($view.name)', '.', 1)
  AND c.relname = split_part('$($view.name)', '.', 2)
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
"@
        $columnResult = Invoke-Psql $admin $columnSql
        if ($columnResult.ExitCode -ne 0) {
            $errors.Add("$($view.name): could not read columns")
            continue
        }
        $actualColumns = @($columnResult.Output | ForEach-Object {
            $parts = $_ -split "`t", 3
            [pscustomobject]@{ name = $parts[0]; postgres_type = $parts[1]; nullable = ($parts[2] -eq 'true') }
        })
        if ($actualColumns.Count -ne $view.columns.Count) {
            $errors.Add("$($view.name): column count expected=$($view.columns.Count) actual=$($actualColumns.Count)")
            continue
        }
        for ($index = 0; $index -lt $view.columns.Count; $index++) {
            $expected = $view.columns[$index]
            $actual = $actualColumns[$index]
            if ($expected.name -ne $actual.name -or
                $expected.postgres_type -ne $actual.postgres_type -or
                [bool]$expected.nullable -ne $actual.nullable) {
                $errors.Add("$($view.name) column $($index + 1): expected $($expected.name)/$($expected.postgres_type)/$($expected.nullable), actual $($actual.name)/$($actual.postgres_type)/$($actual.nullable)")
            }
        }
    }
    @($errors)
}

try {
    foreach ($path in @($catalogFile, $schemaFile, $migrationFile)) {
        Assert-True (Test-Path -LiteralPath $path -PathType Leaf) "required file exists: $path"
    }
    $catalog = Get-Content -Raw -LiteralPath $catalogFile | ConvertFrom-Json -Depth 20
    Assert-True ($catalog.catalog_version -eq '1.0') 'catalog version is 1.0'
    Assert-True ($catalog.postgres_major -eq 17) 'catalog targets PostgreSQL major 17'
    Assert-True ($catalog.views.Count -eq 3) 'catalog contains exactly three semantic views'

    $null = & docker run --detach --rm --name $container `
        --env "POSTGRES_USER=$admin" `
        --env "POSTGRES_PASSWORD=$adminPassword" `
        --env "POSTGRES_DB=$database" `
        $Image
    if ($LASTEXITCODE -ne 0) { throw 'Could not start isolated PostgreSQL container.' }

    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        & docker exec $container pg_isready -U $admin -d $database *> $null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 1
    }
    Assert-True $ready 'isolated PostgreSQL is ready'

    $trackedSchema = Get-Content -Raw -LiteralPath $schemaFile
    $extensionBoundary = $trackedSchema.IndexOf('ALTER TABLE ship_positions')
    Assert-True ($extensionBoundary -gt 0) 'tracked schema 008 contains the PostGIS extension boundary'
    $baseSchema = $trackedSchema.Substring(0, $extensionBoundary)
    $schemaOutput = $baseSchema | & docker exec -i $container psql -X -v ON_ERROR_STOP=1 -U $admin -d $database 2>&1
    if ($LASTEXITCODE -ne 0) { throw "FAIL: SQL-02 source-table fixture schema from 008`n$($schemaOutput -join [Environment]::NewLine)" }
    $checks.Add('four source-table definitions from schema 008 applied in isolated database')

    $fixtureSql = @"
INSERT INTO public.ships (id, mmsi, name, ship_type, flag, imo, callsign)
VALUES (1, '900000001', 'SIM FIXTURE', 'cargo', 'TEST', 'IMO9000001', 'TST01');
INSERT INTO public.ship_positions
    (id, ship_id, latitude, longitude, speed, course, recorded_at, data_source)
VALUES (1, 1, 26.5, 56.5, 12.0, 90.0, '2026-09-21T00:00:00Z', 'simulation');
INSERT INTO public.events
    (id, event_id, event_key, title_zh, summary_zh, event_type, event_datetime,
     mentioned_vessels, coverage_count, perspectives, story_ids,
     publish_date_min, publish_date_max)
VALUES
    (1, 'evt_fixture', 'fixture-key', 'fixture event', 'fixture summary', 'shipping',
     '2026-09-20T12:00:00Z', '[]'::jsonb, 1, '[]'::jsonb, '["news_fixture"]'::jsonb,
     DATE '2026-09-20', DATE '2026-09-20');
INSERT INTO public.news
    (id, story_id, title, url, canonical_url, publish_date, language, media_name,
     perspective, enrich_status, title_zh, summary_zh, event_type,
     mentioned_vessels, relevant, event_id)
VALUES
    (1, 'news_fixture', 'fixture', 'https://example.invalid/raw',
     'https://example.invalid/canonical', DATE '2026-09-20', 'zh', 'fixture source',
     'neutral', 1, 'fixture title', 'fixture summary', 'shipping', '[]'::jsonb, true, 1);
"@
    Assert-PsqlSuccess $admin $fixtureSql 'fixed SQL-02 fixture inserted' | Out-Null

    $migrationOutput = Get-Content -Raw -LiteralPath $migrationFile | & docker exec -i $container psql -X -v ON_ERROR_STOP=1 -U $admin -d $database 2>&1
    if ($LASTEXITCODE -ne 0) { throw "FAIL: migration 013`n$($migrationOutput -join [Environment]::NewLine)" }
    $checks.Add('migration 013 applied')
    $migrationOutput = Get-Content -Raw -LiteralPath $migrationFile | & docker exec -i $container psql -X -v ON_ERROR_STOP=1 -U $admin -d $database 2>&1
    if ($LASTEXITCODE -ne 0) { throw "FAIL: migration 013 idempotency`n$($migrationOutput -join [Environment]::NewLine)" }
    $checks.Add('migration 013 is idempotent')

    $roleRows = Assert-PsqlSuccess $admin @"
SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolcanlogin, rolinherit,
       rolreplication, rolbypassrls, rolconnlimit
FROM pg_roles
WHERE rolname IN ('agent_view_owner', 'agent_reader', 'agent_reader_login')
ORDER BY rolname;
"@ 'role attributes are readable'
    $expectedRoles = @(
        "agent_reader`tf`tf`tf`tf`tf`tf`tf`t-1",
        "agent_reader_login`tf`tf`tf`tt`tt`tf`tf`t4",
        "agent_view_owner`tf`tf`tf`tf`tf`tf`tf`t-1"
    )
    Assert-True ((@($roleRows) -join "`n") -eq ($expectedRoles -join "`n")) 'all three roles have the frozen least-privilege attributes'

    $memberships = Assert-PsqlSuccess $admin @"
SELECT granted.rolname || '->' || member.rolname
FROM pg_auth_members AS m
JOIN pg_roles AS granted ON granted.oid = m.roleid
JOIN pg_roles AS member ON member.oid = m.member
WHERE member.rolname IN ('agent_view_owner', 'agent_reader', 'agent_reader_login')
ORDER BY 1;
"@ 'role memberships are readable'
    Assert-True ((@($memberships) -join '') -eq 'agent_reader->agent_reader_login') 'login has only the agent_reader membership'

    $settings = Assert-PsqlSuccess 'agent_reader_login' "SHOW transaction_read_only; SHOW search_path; SHOW statement_timeout; SHOW lock_timeout; SHOW idle_in_transaction_session_timeout;" 'reader session settings are readable'
    Assert-True ((@($settings) -join ',') -eq 'on,pg_catalog,5s,1s,5s') 'reader is read-only with fixed search path and timeouts'

    foreach ($viewName in @('v_ships', 'v_events', 'v_news')) {
        $count = Assert-PsqlSuccess 'agent_reader_login' "SELECT count(*) FROM agent_data.$viewName;" "reader can select agent_data.$viewName"
        Assert-True ((@($count) -join '').Trim() -eq '1') "agent_data.$viewName returns the fixed fixture row"
    }

    foreach ($tableName in @('ships', 'ship_positions', 'events', 'news')) {
        Assert-PsqlDenied "SELECT count(*) FROM public.$tableName;" "reader cannot select public.$tableName"
    }
    Assert-PsqlDenied "INSERT INTO agent_data.v_news (news_id) VALUES ('blocked');" 'reader cannot insert through a semantic view'
    Assert-PsqlDenied "UPDATE agent_data.v_events SET event_type = 'blocked';" 'reader cannot update a semantic view'
    Assert-PsqlDenied 'DELETE FROM agent_data.v_ships;' 'reader cannot delete from a semantic view'
    Assert-PsqlDenied 'TRUNCATE TABLE public.news;' 'reader cannot truncate a source table'
    Assert-PsqlDenied 'CREATE TABLE public.blocked_ddl (id integer);' 'reader cannot create a public table'
    Assert-PsqlDenied 'CREATE SCHEMA blocked_schema;' 'reader cannot create a schema'
    Assert-PsqlDenied 'DROP VIEW agent_data.v_news;' 'reader cannot drop a semantic view'
    Assert-PsqlDenied 'CREATE TEMP TABLE blocked_temp (id integer);' 'reader cannot create temporary tables'
    Assert-PsqlDenied 'SET ROLE agent_view_owner;' 'reader cannot assume the view owner role'
    Assert-PsqlDenied "SET ROLE $admin;" 'reader cannot assume the administrator role'

    $schemaPrivileges = Assert-PsqlSuccess $admin @"
SELECT has_schema_privilege('agent_reader_login', 'agent_data', 'USAGE'),
       has_schema_privilege('agent_reader_login', 'public', 'USAGE'),
       has_database_privilege('agent_reader_login', current_database(), 'TEMP');
"@ 'effective schema and TEMP privileges are readable'
    Assert-True ((@($schemaPrivileges) -join '').Trim() -eq "t`tf`tf") 'reader has only agent_data schema usage and no TEMP privilege'

    $catalogErrors = @(Compare-Catalog $catalog)
    Assert-True ($catalogErrors.Count -eq 0) ("catalog matches owners, columns, nullability, types, and view hashes" + $(if ($catalogErrors.Count) { ': ' + ($catalogErrors -join '; ') } else { '' }))

    $driftCatalog = ($catalog | ConvertTo-Json -Depth 20 | ConvertFrom-Json -Depth 20)
    $driftCatalog.views[0].definition_sha256 = '0' * 64
    $driftErrors = @(Compare-Catalog $driftCatalog)
    Assert-True ($driftErrors.Count -gt 0) 'catalog validator detects a definition-hash drift'

    Write-Host "PASS: SQL-02 isolated verification completed ($($checks.Count) checks)."
    Write-Host "Container: $container (no host port; isolated database $database)"
}
finally {
    if ($KeepContainer) {
        Write-Warning "Keeping isolated container $container because -KeepContainer was supplied."
    }
    else {
        & docker rm --force $container *> $null
    }
}
