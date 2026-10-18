# -*- coding: utf-8 -*-
"""Native WPF rich-note editor. XamlPackage embeds image bytes with formatting."""
import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')

from System import Convert, Double, Uri, Action
from System.IO import MemoryStream, File
from System.Text import Encoding
from System.Windows import (Clipboard, DataFormats, DataObject, DependencyProperty,
                            MessageBox, Thickness)
from System.Windows.Controls import Image
from System.Windows.Documents import (FlowDocument, Paragraph, Run, TextRange,
                                      InlineUIContainer, TextElement, LogicalDirection)
from System.Windows.Input import Key
from System.Windows.Media import (BrushConverter, FontFamily, Fonts, Stretch,
                                  ScaleTransform)
from System.Windows.Media.Imaging import BitmapImage, BitmapCacheOption, TransformedBitmap
from System.Windows.Threading import DispatcherPriority
from Microsoft.Win32 import OpenFileDialog
from ndev_handy_color_picker import ColorPicker

BUILD = '2026-10-19-safe-sheet-layout-6'

# The editing canvas uses the available viewport; RTF retains A4 paper setup.
EDITOR_MARGIN = 12.0


def configure_editor(document):
    document.PageWidth = Double.NaN
    document.PageHeight = Double.NaN
    document.PagePadding = Thickness(EDITOR_MARGIN)


def full_range(editor):
    return TextRange(editor.Document.ContentStart, editor.Document.ContentEnd)


def plain_text(editor):
    value = full_range(editor).Text
    # WPF adds one document-ending paragraph terminator; retain user blank lines.
    return value[:-2] if value.endswith('\r\n') else value


def pack_document(editor):
    stream = MemoryStream()
    try:
        full_range(editor).Save(stream, DataFormats.XamlPackage)
        return dict(format=u'xaml-package', data=Convert.ToBase64String(stream.ToArray()),
                    page_color=editor.Document.Background.Color.ToString())
    finally:
        stream.Dispose()


def load_document(editor, note):
    document = FlowDocument()
    document.FontFamily = FontFamily('Calibri')
    document.FontSize = 16.0
    document.Foreground = BrushConverter().ConvertFromString('#202C35')
    document.Background = BrushConverter().ConvertFromString('#FFFFFFFF')
    rich = note.get('rich_text')
    if rich:
        stream = MemoryStream(Convert.FromBase64String(rich['data']))
        try:
            TextRange(document.ContentStart, document.ContentEnd).Load(stream, DataFormats.XamlPackage)
        finally:
            stream.Dispose()
        document.Background = BrushConverter().ConvertFromString(rich['page_color'])
    else:
        paragraph = Paragraph()
        paragraph.Inlines.Add(Run(note.get('body', u'')))
        document.Blocks.Add(paragraph)
    # Apply after loading to normalize older notes and pasted page properties.
    configure_editor(document)
    editor.Document = document
    editor.Background = document.Background
    editor.CaretPosition = document.ContentStart


def insert_bitmap(editor, source, width=None):
    if source is None or source.PixelWidth <= 0 or source.PixelHeight <= 0:
        raise ValueError('The image could not be read.')
    # Keep a portable embedded image without retaining a file path or file lock.
    if source.PixelWidth > 1800:
        ratio = 1800.0 / source.PixelWidth
        source = TransformedBitmap(source, ScaleTransform(ratio, ratio))
    if source.CanFreeze:
        source.Freeze()
    image = Image()
    image.Source = source
    image.Width = width or min(480.0, float(source.PixelWidth))
    image.Height = image.Width * source.PixelHeight / source.PixelWidth
    image.Stretch = Stretch.Uniform
    image.Margin = Thickness(0, 6, 0, 6)
    editor.BeginChange()
    try:
        editor.Selection.Text = ''
        point = editor.CaretPosition.GetInsertionPosition(LogicalDirection.Forward)
        container = InlineUIContainer(image, point)
        editor.CaretPosition = container.ElementEnd
    finally:
        editor.EndChange()
    return image


def export_rtf(editor, path):
    stream = MemoryStream()
    try:
        full_range(editor).Save(stream, DataFormats.Rtf)
        rtf = Encoding.ASCII.GetString(stream.ToArray())
    finally:
        stream.Dispose()
    # TextRange exports content, so explicitly supply Word's paper setup in
    # twips (1440 per inch). Leave all text, formatting and pictures intact.
    header = r'{\rtf1'
    if not rtf.startswith(header):
        raise ValueError('The formatted note could not be exported as RTF.')
    setup = r'\paperw11906\paperh16838\margl1134\margr1134\margt1134\margb1134'
    rtf = header + setup + rtf[len(header):]
    File.WriteAllText(path, rtf, Encoding.ASCII)


class RichNoteEditor(object):
    def __init__(self, window, changed):
        self.window, self.editor, self.changed = window, window.body_editor, changed
        self.updating = True
        self.selected_image = None
        self.color_picker = None
        self.layout_pending = False
        self.disposed = False
        for family in sorted(set(font.Source for font in Fonts.SystemFontFamilies)):
            window.font_combo.Items.Add(family)
        for size in (8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28, 32, 36, 48, 72):
            window.size_combo.Items.Add(str(size))
        window.font_combo.SelectedItem = 'Calibri'
        window.size_combo.Text = '12'
        window.font_combo.SelectionChanged += self.font_changed
        window.size_combo.SelectionChanged += self.size_changed
        window.size_combo.PreviewKeyDown += self.size_key
        window.size_combo.LostKeyboardFocus += self.size_lost_focus
        window.text_color_button.Click += self.text_color
        window.highlight_button.Click += self.highlight
        window.clear_highlight_button.Click += self.clear_highlight
        window.page_color_button.Click += self.page_color
        window.image_button.Click += self.add_image
        window.paste_image_button.Click += self.paste_image
        window.resize_image_button.Click += self.resize_image
        self.editor.Loaded += self.layout_ready
        self.editor.SelectionChanged += self.selection_changed
        self.editor.PreviewMouseLeftButtonDown += self.image_clicked
        DataObject.AddPastingHandler(self.editor, self.pasting)
        self.updating = False

    def layout_ready(self, sender, args):
        if self.disposed or self.layout_pending:
            return
        self.layout_pending = True
        self.editor.Dispatcher.BeginInvoke(DispatcherPriority.Loaded, Action(self.apply_layout))

    def apply_layout(self):
        self.layout_pending = False
        if self.disposed:
            return
        try:
            # Apply once after WPF creates the render scope for the new document.
            # Never change document layout from the global LayoutUpdated event.
            configure_editor(self.editor.Document)
        except Exception as error:
            self.window.status_text.Text = 'Could not update the note layout: {}'.format(error)

    def dispose(self):
        self.disposed = True
        self.close_color_picker()
        self.editor.Loaded -= self.layout_ready

    def load(self, note):
        self.close_color_picker()
        self.updating = True
        try:
            load_document(self.editor, note)
            self.selected_image = None
            self.layout_ready(None, None)
        finally:
            self.updating = False
        self.selection_changed(None, None)

    def apply(self, property_id, value, focus=True):
        self.editor.Selection.ApplyPropertyValue(property_id, value)
        if focus:
            self.editor.Focus()
        self.changed(None, None)

    def font_changed(self, sender, args):
        if not self.updating and self.window.font_combo.SelectedItem:
            self.apply(TextElement.FontFamilyProperty, FontFamily(self.window.font_combo.SelectedItem))

    def apply_size(self, focus=True):
        if self.updating:
            return
        try:
            points = float(self.window.size_combo.Text)
            if Double.IsNaN(points) or Double.IsInfinity(points) or not 1 <= points <= 200:
                raise ValueError('Enter a font size from 1 to 200 points.')
            self.apply(TextElement.FontSizeProperty, points * 96.0 / 72.0, focus=focus)
        except Exception as error:
            MessageBox.Show(self.window, str(error), 'Font size')

    def size_changed(self, sender, args):
        if not self.updating and self.window.size_combo.SelectedItem is not None:
            # Editable ComboBox.Text may update after SelectionChanged.
            self.window.size_combo.Text = str(self.window.size_combo.SelectedItem)
            self.apply_size()

    def size_key(self, sender, args):
        if args.Key == Key.Enter:
            args.Handled = True
            self.apply_size()

    def size_lost_focus(self, sender, args):
        if not self.updating and self.window.size_combo.IsKeyboardFocusWithin == False:
            self.apply_size(focus=False)

    def close_color_picker(self):
        if self.color_picker is not None:
            self.color_picker.close()

    def pick_color(self, target, title, current, callback):
        try:
            if self.color_picker is None:
                self.color_picker = ColorPicker(self.window)
            self.color_picker.open(target, title, current, callback)
        except Exception as error:
            self.window.status_text.Text = 'Could not open the color palette: {}'.format(error)

    def selection_color(self, target, title, property_id):
        document = self.editor.Document
        start, end = self.editor.Selection.Start, self.editor.Selection.End
        def apply_color(brush):
            if self.editor.Document == document:
                self.editor.Selection.Select(start, end)
                self.apply(property_id, brush)
        self.pick_color(target, title, self.editor.Selection.GetPropertyValue(property_id), apply_color)

    def text_color(self, sender, args):
        self.selection_color(self.window.text_color_button, 'Text color', TextElement.ForegroundProperty)

    def highlight(self, sender, args):
        self.selection_color(self.window.highlight_button, 'Highlight color', TextElement.BackgroundProperty)

    def clear_highlight(self, sender, args):
        self.close_color_picker()
        try:
            self.apply(TextElement.BackgroundProperty, BrushConverter().ConvertFromString('#00FFFFFF'))
        except Exception as error:
            self.window.status_text.Text = 'Highlight was not cleared: {}'.format(error)

    def page_color(self, sender, args):
        document = self.editor.Document
        def apply_color(brush):
            if self.editor.Document == document:
                document.Background = brush
                self.editor.Background = brush
                self.changed(None, None)
        self.pick_color(self.window.page_color_button, 'Page color', document.Background, apply_color)

    def add_image(self, sender, args):
        dialog = OpenFileDialog()
        dialog.Title = 'Insert image'
        dialog.Filter = 'Images|*.png;*.jpg;*.jpeg;*.bmp;*.gif;*.tif;*.tiff|All files|*.*'
        if dialog.ShowDialog(self.window) == True:
            try:
                bitmap = BitmapImage()
                bitmap.BeginInit()
                bitmap.CacheOption = BitmapCacheOption.OnLoad
                bitmap.UriSource = Uri(dialog.FileName)
                bitmap.EndInit()
                self.selected_image = insert_bitmap(self.editor, bitmap)
                self.window.image_width.Text = '{:.0f}'.format(self.selected_image.Width)
                self.editor.Focus()
                self.changed(None, None)
            except Exception as error:
                MessageBox.Show(self.window, 'Could not insert this image:\n{}'.format(error), 'Notes')

    def paste_image(self, sender, args):
        try:
            if not Clipboard.ContainsImage():
                MessageBox.Show(self.window, 'Copy an image or screenshot first, then choose Paste image.', 'Notes')
                return
            self.selected_image = insert_bitmap(self.editor, Clipboard.GetImage())
            self.window.image_width.Text = '{:.0f}'.format(self.selected_image.Width)
            self.editor.Focus()
            self.changed(None, None)
        except Exception as error:
            MessageBox.Show(self.window, 'Could not paste this image:\n{}'.format(error), 'Notes')

    def pasting(self, sender, args):
        # Preserve normal rich-text paste. Intercept bitmap-only clipboard data.
        if args.DataObject.GetDataPresent(DataFormats.Bitmap) and not (
                args.DataObject.GetDataPresent(DataFormats.Rtf) or args.DataObject.GetDataPresent(DataFormats.XamlPackage)):
            args.CancelCommand()
            self.paste_image(None, None)

    def image_clicked(self, sender, args):
        image = args.OriginalSource
        if isinstance(image, Image) and isinstance(image.Parent, InlineUIContainer):
            self.selected_image = image
            self.window.image_width.Text = '{:.0f}'.format(image.Width)
            self.editor.Selection.Select(image.Parent.ElementStart, image.Parent.ElementEnd)
            self.editor.Focus()
            args.Handled = True
            self.window.status_text.Text = 'Image selected. Change width and click Resize, or press Delete.'

    def resize_image(self, sender, args):
        image = self.selected_image
        if image is None or image.Parent is None:
            MessageBox.Show(self.window, 'Click an image in this note first.', 'Resize image')
            return
        try:
            width = float(self.window.image_width.Text)
            if Double.IsNaN(width) or Double.IsInfinity(width) or not 20 <= width <= 2000:
                raise ValueError('Enter an image width from 20 to 2000.')
            image.Width = width
            image.Height = width * image.Source.PixelHeight / image.Source.PixelWidth
            self.editor.Focus()
            self.changed(None, None)
        except Exception as error:
            MessageBox.Show(self.window, str(error), 'Resize image')

    def selection_changed(self, sender, args):
        if self.updating:
            return
        self.updating = True
        try:
            family = self.editor.Selection.GetPropertyValue(TextElement.FontFamilyProperty)
            size = self.editor.Selection.GetPropertyValue(TextElement.FontSizeProperty)
            self.window.font_combo.SelectedItem = family.Source if isinstance(family, FontFamily) else None
            self.window.size_combo.Text = '{:g}'.format(float(size) * 72.0 / 96.0) if size != DependencyProperty.UnsetValue else ''
        finally:
            self.updating = False
