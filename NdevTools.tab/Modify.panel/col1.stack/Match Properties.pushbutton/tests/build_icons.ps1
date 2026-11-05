$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName PresentationCore, WindowsBase
$bundle = Split-Path -Parent $PSScriptRoot
foreach ($theme in @('light', 'dark')) {
    $svg = [xml](Get-Content -LiteralPath (Join-Path $bundle ('assets\icon.' + $theme + '.svg')) -Raw)
    $geometry = [Windows.Media.Geometry]::Parse($svg.svg.path.d)
    $brush = New-Object Windows.Media.SolidColorBrush ([Windows.Media.ColorConverter]::ConvertFromString($svg.svg.path.stroke))
    $pen = New-Object Windows.Media.Pen $brush, 3
    $pen.LineJoin = [Windows.Media.PenLineJoin]::Round
    $pen.StartLineCap = [Windows.Media.PenLineCap]::Round
    $pen.EndLineCap = [Windows.Media.PenLineCap]::Round
    $visual = New-Object Windows.Media.DrawingVisual
    $drawing = $visual.RenderOpen()
    $drawing.DrawGeometry($null, $pen, $geometry)
    $drawing.Close()
    $bitmap = New-Object Windows.Media.Imaging.RenderTargetBitmap 64, 64, 96, 96, ([Windows.Media.PixelFormats]::Pbgra32)
    $bitmap.Render($visual)
    $encoder = New-Object Windows.Media.Imaging.PngBitmapEncoder
    $encoder.Frames.Add([Windows.Media.Imaging.BitmapFrame]::Create($bitmap))
    $filename = if ($theme -eq 'dark') { 'icon.dark.png' } else { 'icon.png' }
    $stream = [IO.File]::Create((Join-Path $bundle $filename))
    try { $encoder.Save($stream) } finally { $stream.Dispose() }
    Write-Output ('Created ' + $filename)
}
