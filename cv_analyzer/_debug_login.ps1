$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$r = Invoke-WebRequest -UseBasicParsing -WebSession $session http://127.0.0.1:5000/login
Write-Output ('GET=' + $r.StatusCode)
Write-Output ('COOKIE=' + (($session.Cookies.GetCookies('http://127.0.0.1:5000') | ForEach-Object { $_.Name + '=' + $_.Value }) -join '; '))
$csrf = ([regex]::Match($r.Content, 'name="csrf_token" value="([^"]+)"')).Groups[1].Value
Write-Output ('CSRF_FOUND=' + [bool]$csrf)
$body = @{ username='admin_user'; password='StrongLocalPassw0rd!'; csrf_token=$csrf }
try {
    $p = Invoke-WebRequest -UseBasicParsing -WebSession $session -Method Post -Uri http://127.0.0.1:5000/login -Body $body -ContentType 'application/x-www-form-urlencoded' -ErrorAction Stop
    Write-Output ('POST=' + $p.StatusCode)
    Write-Output ('LOCATION=' + $p.Headers.Location)
    Write-Output ('RESP=' + $p.Content.Substring(0,[Math]::Min(300,$p.Content.Length)))
} catch {
    if ($_.Exception.Response) {
        Write-Output ('POST=' + [int]$_.Exception.Response.StatusCode)
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        $text = $reader.ReadToEnd()
        Write-Output ('RESP=' + $text.Substring(0,[Math]::Min(300,$text.Length)))
    } else {
        Write-Output $_.Exception.Message
    }
}
