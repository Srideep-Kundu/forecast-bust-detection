$ErrorActionPreference = "Stop"

forecast-bust build-full
if ($LASTEXITCODE -ne 0) { throw "build-full failed with exit code $LASTEXITCODE" }

forecast-bust label
if ($LASTEXITCODE -ne 0) { throw "label failed with exit code $LASTEXITCODE" }

forecast-bust train
if ($LASTEXITCODE -ne 0) { throw "train failed with exit code $LASTEXITCODE" }
