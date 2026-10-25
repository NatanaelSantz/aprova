# Janela de instalação do Python (usada pelo "Abrir Aprova.bat" quando o computador não tem Python).
param([string]$Url = "https://www.python.org/ftp/python/3.13.16/python-3.13.16-amd64.exe")

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$raiz = Split-Path -Parent $PSScriptRoot
$azul = [System.Drawing.Color]::FromArgb(35, 64, 168)
$cinza = [System.Drawing.Color]::FromArgb(88, 97, 121)

$form = New-Object System.Windows.Forms.Form
$form.Text = "Aprova - instalação"
$form.ClientSize = New-Object System.Drawing.Size(500, 230)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedSingle"
$form.MaximizeBox = $false
$form.BackColor = [System.Drawing.Color]::White
$ico = Join-Path $raiz "assets\aprova.ico"
if (Test-Path $ico) { $form.Icon = New-Object System.Drawing.Icon($ico) }

$png = Join-Path $raiz "assets\icon.png"
if (Test-Path $png) {
    $logo = New-Object System.Windows.Forms.PictureBox
    $logo.Image = [System.Drawing.Image]::FromFile($png)
    $logo.SizeMode = "Zoom"
    $logo.Location = New-Object System.Drawing.Point(28, 26)
    $logo.Size = New-Object System.Drawing.Size(60, 60)
    $form.Controls.Add($logo)
}

$titulo = New-Object System.Windows.Forms.Label
$titulo.Text = "Preparando o Aprova"
$titulo.Font = New-Object System.Drawing.Font("Segoe UI Semibold", 15)
$titulo.ForeColor = [System.Drawing.Color]::FromArgb(20, 28, 51)
$titulo.Location = New-Object System.Drawing.Point(104, 26)
$titulo.AutoSize = $true
$form.Controls.Add($titulo)

$sub = New-Object System.Windows.Forms.Label
$sub.Text = "Instalando o Python, que o Aprova usa para funcionar." + [Environment]::NewLine + "Isso acontece só uma vez."
$sub.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$sub.ForeColor = $cinza
$sub.Location = New-Object System.Drawing.Point(106, 60)
$sub.Size = New-Object System.Drawing.Size(370, 44)
$form.Controls.Add($sub)

$barra = New-Object System.Windows.Forms.ProgressBar
$barra.Style = "Marquee"
$barra.MarqueeAnimationSpeed = 25
$barra.Location = New-Object System.Drawing.Point(28, 130)
$barra.Size = New-Object System.Drawing.Size(444, 12)
$form.Controls.Add($barra)

$status = New-Object System.Windows.Forms.Label
$status.Text = "Começando…"
$status.Font = New-Object System.Drawing.Font("Segoe UI", 9.5)
$status.ForeColor = $cinza
$status.Location = New-Object System.Drawing.Point(28, 154)
$status.Size = New-Object System.Drawing.Size(444, 40)
$form.Controls.Add($status)

$job = Start-Job -ArgumentList $Url -ScriptBlock {
    param($Url)
    $ok = $false
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install -e --id Python.Python.3.13 --source winget --scope user --silent --accept-package-agreements --accept-source-agreements | Out-Null
        if ($LASTEXITCODE -eq 0) { $ok = $true }
        if (-not $ok) {
            winget install -e --id Python.Python.3.13 --source winget --silent --accept-package-agreements --accept-source-agreements | Out-Null
            if ($LASTEXITCODE -eq 0) { $ok = $true }
        }
    }
    if (-not $ok) {
        $inst = Join-Path $env:TEMP "python-aprova.exe"
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $inst
        Start-Process -FilePath $inst -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 InstallLauncherAllUsers=0 Include_test=0" -Wait
        Remove-Item $inst -ErrorAction SilentlyContinue
    }
}

$inicio = Get-Date
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 1000
$timer.Add_Tick({
    $seg = [int]((Get-Date) - $inicio).TotalSeconds
    $m = [math]::Floor($seg / 60); $s = $seg % 60
    $status.Text = ("Instalando o Python… {0}:{1:D2}" -f $m, $s) + [Environment]::NewLine + "Pode levar de 2 a 5 minutos. Não feche esta janela."
    if ($job.State -ne "Running") { $timer.Stop(); $form.Close() }
})
$form.Add_Shown({ $timer.Start(); $form.Activate() })
[void]$form.ShowDialog()
Wait-Job $job | Out-Null
Remove-Job $job -Force
