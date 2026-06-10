$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..")
$dockerfile = Join-Path $repoRoot "apps\cs_auto\deploy\docker\airflow.Dockerfile"
$imageTag = "skn25-cs-auto-airflow:verify"

Write-Host "Building Airflow image: $imageTag"
docker build -f $dockerfile -t $imageTag $repoRoot
if ($LASTEXITCODE -ne 0) {
    throw "docker build failed with exit code $LASTEXITCODE"
}

Write-Host "Verifying deployed files inside image"
docker run --rm --entrypoint /bin/sh $imageTag -lc "test -f /opt/airflow/cs_auto_backend/agents/answer_agent.py && test -f /opt/airflow/cs_auto_backend/airflow/answer_agent_dag.py && echo verified:/opt/airflow/cs_auto_backend/agents/answer_agent.py && echo verified:/opt/airflow/cs_auto_backend/airflow/answer_agent_dag.py"
if ($LASTEXITCODE -ne 0) {
    throw "docker run verification failed with exit code $LASTEXITCODE"
}
