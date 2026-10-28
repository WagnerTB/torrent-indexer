param(
    [string]$BaseUrl = "http://localhost:7006",
    [int]$TimeoutSeconds = 45,
    [string]$Query = "matrix",
    [string[]]$Indexers = @(
        "torrent-dos-filmes",
        "rede_torrent",
        "starck-filmes",
        "comando_torrents",
        "bludv",
        "vaca_torrent"
    )
)

$ErrorActionPreference = "Continue"

Write-Host "Testing $BaseUrl with ${TimeoutSeconds}s timeout per indexer"
Write-Host "Start the server in another terminal before running this script."
Write-Host ""

$rows = foreach ($indexer in $Indexers) {
    $url = "$BaseUrl/indexers/$indexer?q=$Query"
    $tmp = [System.IO.Path]::GetTempFileName()
    $started = Get-Date

    try {
        $http = & curl.exe -s -o $tmp -w "%{http_code}" --max-time $TimeoutSeconds $url 2>&1
        $seconds = [math]::Round(((Get-Date) - $started).TotalSeconds, 1)
        $body = Get-Content -LiteralPath $tmp -Raw -ErrorAction SilentlyContinue
        $count = ""
        $errorMessage = ""

        if ($body) {
            try {
                $json = $body | ConvertFrom-Json
                $count = $json.count
                if ($json.error) {
                    $errorMessage = $json.error
                }
            } catch {
                $errorMessage = $body.Substring(0, [Math]::Min(120, $body.Length))
            }
        }

        [pscustomobject]@{
            Indexer = $indexer
            HTTP    = $http
            Seconds = $seconds
            Count   = $count
            Error   = $errorMessage
        }
    } finally {
        Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
    }
}

$rows | Format-Table -AutoSize
