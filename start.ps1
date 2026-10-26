$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (!(Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker не найден. Установите Docker Desktop и включите Linux containers / WSL 2.'
}
docker info --format '{{.ServerVersion}}'
if ($LASTEXITCODE -ne 0) {
    throw 'Docker Engine недоступен. Запустите Docker Desktop, дождитесь готовности Engine и повторите start.ps1.'
}
docker compose version
if ($LASTEXITCODE -ne 0) { throw 'Нужен Docker Compose v2 из Docker Desktop.' }
if (!(Test-Path .env)) { throw 'Создайте .env: Copy-Item .env.example .env; задайте POSTGRES_PASSWORD.' }
Remove-Item Env:OLLAMA_ENDPOINT -ErrorAction SilentlyContinue
docker compose build app db
if ($LASTEXITCODE -ne 0) { throw 'Ошибка сборки Docker. См. вывод выше.' }
docker compose run --rm --no-deps probe
$probeStatus = $LASTEXITCODE
if ($probeStatus -eq 2) {
    $env:OLLAMA_ENDPOINT = 'http://ollama:11434'
    docker compose --profile bundled up -d ollama
    if ($LASTEXITCODE -ne 0) { throw 'Ошибка запуска Ollama.' }
} elseif ($probeStatus -ne 0) {
    throw "Проверка Ollama завершилась ошибкой ($probeStatus). См. вывод выше."
}
docker compose up -d db init model-init
if ($LASTEXITCODE -ne 0) { throw 'Ошибка запуска БД или init.' }
docker compose logs -f model-init
if ($LASTEXITCODE -ne 0) { throw 'Ошибка чтения логов model-init.' }
$modelContainer = docker compose ps --all --quiet model-init
if ($LASTEXITCODE -ne 0 -or !$modelContainer) { throw 'Контейнер model-init не найден.' }
$modelState = docker inspect --format '{{.State.Status}} {{.State.ExitCode}}' $modelContainer
if ($LASTEXITCODE -ne 0 -or $modelState -ne 'exited 0') { throw "Модель не готова ($modelState). См. docker compose logs model-init." }
docker compose up -d --no-deps app
if ($LASTEXITCODE -ne 0) { throw 'Ошибка запуска кабинета.' }
$appContainer = docker compose ps --all --quiet app
if ($LASTEXITCODE -ne 0 -or !$appContainer) { throw 'Контейнер кабинета не найден.' }
$appReady = $false
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    $appState = docker inspect --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' $appContainer
    if ($LASTEXITCODE -ne 0) { throw 'Не удалось проверить состояние кабинета.' }
    if ($appState -eq 'running healthy') { $appReady = $true; break }
    if ($appState -match '^(exited|dead)' -or $appState -match 'unhealthy$') {
        throw "Кабинет не готов ($appState). См. docker compose logs app."
    }
    Start-Sleep -Seconds 2
}
if (!$appReady) { throw 'Кабинет не стал готов за 120 секунд. См. docker compose logs app.' }
Write-Host 'Кабинет запущен. Статус: docker compose ps; логи: docker compose logs -f app'
