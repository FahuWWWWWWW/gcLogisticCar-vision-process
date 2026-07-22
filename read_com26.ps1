$port = New-Object System.IO.Ports.SerialPort COM26,115200,None,8,One
$port.Open()
Start-Sleep -Seconds 2
$output = $port.ReadExisting()
$port.Close()
Write-Output $output
