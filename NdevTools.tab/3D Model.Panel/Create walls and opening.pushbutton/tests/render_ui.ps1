# Render the actual XAML with sample data, without opening a desktop window.
Add-Type -AssemblyName PresentationFramework
Add-Type -AssemblyName PresentationCore
$root = Split-Path $PSScriptRoot
$window = [Windows.Markup.XamlReader]::Parse([IO.File]::ReadAllText((Join-Path $root 'WallTracing.xaml')))
$window.FindName('brand_logo').Source = [Windows.Media.Imaging.BitmapImage]::new([Uri](Join-Path $root 'reference\NdevTools_Logo.png'))
$window.FindName('link_combo').Items.Add('Architectural model.rvt [ID 12480]') | Out-Null
$window.FindName('link_combo').SelectedIndex = 0
$window.FindName('link_info').Text = "File: Architectural model.rvt`nPath: C:\Projects\Architectural model.rvt`nStatus: Loaded    |    Total Levels: 8"
$window.FindName('selection_count').Text = '3 of 8 levels selected'
function New-Row($widths) {
    $grid = [Windows.Controls.Grid]::new()
    foreach ($width in $widths) {
        $column = [Windows.Controls.ColumnDefinition]::new()
        $column.Width = [Windows.GridLength]::new($width, [Windows.GridUnitType]::Star)
        $grid.ColumnDefinitions.Add($column)
    }
    return $grid
}
function Add-Text($grid, $column, $value) {
    $text = [Windows.Controls.TextBlock]::new()
    $text.Text = $value
    $text.TextWrapping = 'Wrap'
    $text.Margin = [Windows.Thickness]::new(8,7,8,7)
    [Windows.Controls.Grid]::SetColumn($text,$column)
    $grid.Children.Add($text) | Out-Null
}
foreach ($i in 1..8) {
    $row = New-Row @(0.5,3,1.5,0.8)
    Add-Text $row 0 "$i"
    Add-Text $row 1 "Level $i"
    Add-Text $row 2 "$($i*10-10)' - 0`""
    $check = [Windows.Controls.CheckBox]::new()
    $check.IsChecked = $i -le 3
    [Windows.Controls.Grid]::SetColumn($check,3)
    $row.Children.Add($check) | Out-Null
    $window.FindName('level_rows').Children.Add($row) | Out-Null
}
foreach ($level in 1..3) {
    $card = [Windows.Controls.Border]::new()
    $card.Style = $window.FindResource('Card')
    $card.Margin = [Windows.Thickness]::new(0,0,0,12)
    $panel = [Windows.Controls.StackPanel]::new()
    $card.Child = $panel
    $heading = [Windows.Controls.TextBlock]::new()
    $heading.Text = "Level $level | Elevation: $($level*10-10)' - 0`" | 24 source walls"
    $heading.FontSize = 18
    $heading.Margin = [Windows.Thickness]::new(8)
    $panel.Children.Add($heading) | Out-Null
    $labels = New-Row @(1,1)
    Add-Text $labels 0 'Host Bottom Level'
    Add-Text $labels 1 'Host Top Level'
    $panel.Children.Add($labels) | Out-Null
    $choices = New-Row @(1,1)
    foreach ($col in 0..1) {
        $combo = [Windows.Controls.ComboBox]::new()
        $combo.Items.Add("Level $($level+$col)") | Out-Null
        $combo.SelectedIndex = 0
        $combo.Margin = [Windows.Thickness]::new(5)
        [Windows.Controls.Grid]::SetColumn($combo,$col)
        $choices.Children.Add($combo) | Out-Null
    }
    $panel.Children.Add($choices) | Out-Null
    $row = New-Row @(0.3,2.1,1,1.8,2.5)
    $headings = @('#','Architectural Wall Type','Structure [1] thickness','Detected Layer / Material','Host Wall Type')
    foreach ($col in 0..4) { Add-Text $row $col $headings[$col] }
    $panel.Children.Add($row) | Out-Null
    foreach ($i in 1..3) {
        $row = New-Row @(0.3,2.1,1,1.8,2.5)
        Add-Text $row 0 "$i"
        Add-Text $row 1 "Exterior Wall - $i"
        Add-Text $row 2 '6"'
        Add-Text $row 3 'Layer 3: Metal Stud'
        $combo = [Windows.Controls.ComboBox]::new()
        $combo.Items.Add('None') | Out-Null
        $combo.Items.Add('6" Structural Stud [ID 28218]') | Out-Null
        $combo.SelectedIndex = 1
        $combo.Margin = [Windows.Thickness]::new(5)
        [Windows.Controls.Grid]::SetColumn($combo,4)
        $row.Children.Add($combo) | Out-Null
        $panel.Children.Add($row) | Out-Null
    }
    $window.FindName('mapping_panels').Children.Add($card) | Out-Null
}
# Preserve Window resources/inherited text properties while rendering off-screen.
$content = $window.Content
$window.Content = $null
$frame = [Windows.Controls.Border]::new()
$frame.Resources = $window.Resources
$frame.Background = $window.Background
[Windows.Documents.TextElement]::SetForeground($frame,$window.Foreground)
[Windows.Documents.TextElement]::SetFontFamily($frame,$window.FontFamily)
[Windows.Documents.TextElement]::SetFontSize($frame,$window.FontSize)
$frame.Child = $content
foreach ($page in 1..2) {
    if ($page -eq 2) {
        $window.FindName('page_one').Visibility = 'Collapsed'
        $window.FindName('page_two').Visibility = 'Visible'
        $window.FindName('back_button').Visibility = 'Visible'
        $window.FindName('next_button').Content = 'Create Walls'
        $window.FindName('step_one').Background = [Windows.Media.BrushConverter]::new().ConvertFromString('#0B2A3D')
        $window.FindName('step_two').Background = [Windows.Media.BrushConverter]::new().ConvertFromString('#00C6E8')
        $window.FindName('step_one_text').Foreground = [Windows.Media.BrushConverter]::new().ConvertFromString('#8DB6CC')
        $window.FindName('step_two_text').Foreground = [Windows.Media.BrushConverter]::new().ConvertFromString('#031A28')
    }
    $frame.Measure([Windows.Size]::new(1080,780))
    $frame.Arrange([Windows.Rect]::new(0,0,1080,780))
    $frame.UpdateLayout()
    $bitmap = [Windows.Media.Imaging.RenderTargetBitmap]::new(1080,780,96,96,[Windows.Media.PixelFormats]::Pbgra32)
    $bitmap.Render($frame)
    $encoder = [Windows.Media.Imaging.PngBitmapEncoder]::new()
    $encoder.Frames.Add([Windows.Media.Imaging.BitmapFrame]::Create($bitmap))
    $stream = [IO.File]::Create((Join-Path $root "reference\ui-page$page-preview.png"))
    $encoder.Save($stream)
    $stream.Dispose()
    Write-Output "WPF page $page rendered with sample data."
}
