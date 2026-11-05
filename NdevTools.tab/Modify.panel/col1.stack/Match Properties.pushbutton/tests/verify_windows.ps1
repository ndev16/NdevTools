param([string]$OutputDirectory = $env:TEMP)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName PresentationFramework, PresentationCore, WindowsBase
$bundle = Split-Path -Parent $PSScriptRoot

foreach ($name in @('MatchProperties', 'Report', 'PropertySelection')) {
    $reader = New-Object System.Xml.XmlNodeReader ([xml](Get-Content -LiteralPath (Join-Path $bundle ($name + '.xaml')) -Raw -Encoding UTF8))
    $window = [Windows.Markup.XamlReader]::Load($reader)
    if ($name -eq 'Report') {
        $window.FindName('summary').Text = '2 updated  |  1 already matched  |  1 with exceptions'
        $window.FindName('report_text').Text = "NdevTools - Match Properties`n`nSOURCE / Length: Calculated or read-only; Revit maintains this value.`n`nTARGET 1250 - Updated`nType: Matched source type`n  Comments | Copied`n  z Justification | Copied`n  z Offset Value | Copied`n`nTARGET 1251 - Already matches`nType: Already matches`n`nTARGET 1252 - Skipped`n  Pinned element retained; unpin it to match properties."
    } elseif ($name -eq 'PropertySelection') {
        $window.FindName('source_label').Text = 'Beam - sample source'
        foreach ($label in @('Element type (includes shared type properties)', 'Reference Level | First Floor', 'Structural Material | Wood', 'Structural Usage | Girder', 'Comments | Source note')) {
            $box = New-Object Windows.Controls.CheckBox
            $box.Content = $label
            $box.IsChecked = $true
            $window.FindName('property_rows').Children.Add($box) | Out-Null
        }
        $window.FindName('notes').Text = 'Calculated fields are omitted. Target read-only fields are reported.'
    } else {
        $bitmap = New-Object Windows.Media.Imaging.BitmapImage
        $bitmap.BeginInit()
        $bitmap.CacheOption = [Windows.Media.Imaging.BitmapCacheOption]::OnLoad
        $bitmap.UriSource = New-Object System.Uri (Join-Path $bundle 'assets\ndevtools-logo.png')
        $bitmap.EndInit()
        $window.FindName('brand_image').Source = $bitmap
    }
    # Layout off-screen. No app/window is displayed or activated.
    $content = $window.Content
    $window.Content = $null
    $surface = New-Object Windows.Controls.Border
    $surface.Background = $window.Background
    $surface.Resources = $window.Resources
    $surface.Child = $content
    [Windows.Controls.TextBlock]::SetFontFamily($surface, $window.FontFamily)
    [Windows.Controls.TextBlock]::SetFontSize($surface, $window.FontSize)
    [Windows.Controls.TextBlock]::SetForeground($surface, $window.Foreground)
    $width, $height = [int]$window.Width, [int]$window.Height
    $surface.Measure((New-Object Windows.Size $width, $height))
    $surface.Arrange((New-Object Windows.Rect 0, 0, $width, $height))
    $surface.UpdateLayout()
    $image = New-Object Windows.Media.Imaging.RenderTargetBitmap $width, $height, 96, 96, ([Windows.Media.PixelFormats]::Pbgra32)
    $image.Render($surface)
    $encoder = New-Object Windows.Media.Imaging.PngBitmapEncoder
    $encoder.Frames.Add([Windows.Media.Imaging.BitmapFrame]::Create($image))
    $stream = [IO.File]::Create((Join-Path $OutputDirectory ($name + '-preview.png')))
    try { $encoder.Save($stream) } finally { $stream.Dispose() }
    Write-Output ($name + ': WPF loaded and rendered at ' + $width + 'x' + $height)
    $window.Close()
}

# Compile against the installed pyRevit IronPython 2.7 engine without running Revit code.
$engineDirectory = Join-Path $env:APPDATA 'pyRevit-Master\bin\netfx\engines\IPY2712PR'
foreach ($dll in @('pyRevitLabs.Microsoft.Scripting.dll', 'pyRevitLabs.Microsoft.Dynamic.dll', 'pyRevitLabs.IronPython.dll')) {
    [Reflection.Assembly]::LoadFrom((Join-Path $engineDirectory $dll)) | Out-Null
}
$engine = [IronPython.Hosting.Python]::CreateEngine()
foreach ($file in Get-ChildItem -LiteralPath $bundle -Filter '*.py') {
    $engine.CreateScriptSourceFromFile($file.FullName).Compile() | Out-Null
    Write-Output ('IronPython compiled: ' + $file.Name)
}
