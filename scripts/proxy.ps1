$ErrorActionPreference = 'Stop'
$proxyValues = @{
    HTTP_PROXY = 'http://127.0.0.1:7897'
    HTTPS_PROXY = 'http://127.0.0.1:7897'
    ALL_PROXY = 'socks5://127.0.0.1:7898'
    NO_PROXY = 'localhost,127.0.0.1,::1'
}
foreach ($proxyName in $proxyValues.Keys) {
    Set-Item -Path "Env:$proxyName" -Value $proxyValues[$proxyName]
    Set-Item -Path "Env:$($proxyName.ToLowerInvariant())" -Value $proxyValues[$proxyName]
}
$proxyClient = New-Object System.Net.Sockets.TcpClient
try {
    $proxyAttempt = $proxyClient.ConnectAsync('127.0.0.1', 7897)
    if (-not $proxyAttempt.Wait(800) -or -not $proxyClient.Connected) {
        throw 'Proxy unavailable'
    }
} catch {
    throw '本机代理 127.0.0.1:7897 不可用，已停止。请启动 Clash/Mihomo，禁止直连回退。'
} finally {
    $proxyClient.Dispose()
}
