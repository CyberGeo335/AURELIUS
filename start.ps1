$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (!(Test-Path .env)) { throw 'Создайте .env: Copy-Item .env.example .env; задайте POSTGRES_PASSWORD.' }
Remove-Item Env:OLLAMA_ENDPOINT -ErrorAction SilentlyContinue
docker compose build app
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
Write-Host 'Кабинет запущен. Статус: docker compose ps; логи: docker compose logs -f app'
