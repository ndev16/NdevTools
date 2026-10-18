# -*- coding: utf-8 -*-
"""Export all note sheets through one native WPF RTF resource table."""
import clr
clr.AddReference('PresentationFramework')
from System import Guid
from System.IO import MemoryStream, File
from System.Text import Encoding
from System.Text.RegularExpressions import Regex
from System.Windows import DataFormats
from System.Windows.Controls import RichTextBox
from System.Windows.Documents import FlowDocument, Paragraph, Run, TextRange
from System.Windows.Media import FontFamily, Brushes
from ndev_handy_richtext import load_document


def _section_setup(orientation):
    if orientation not in ('portrait', 'landscape'):
        raise ValueError('Choose Portrait or Landscape for every sheet.')
    width, height = (16838, 11906) if orientation == 'landscape' else (11906, 16838)
    return (r'\sectd\sbkpage\pgwsxn%d\pghsxn%d'
            r'\marglsxn1134\margrsxn1134\margtsxn1134\margbsxn1134%s '
            % (width, height, r'\lndscpsxn' if orientation == 'landscape' else ''))


def _sheet_markers(rtf, tokens):
    """Locate whole native marker paragraphs without touching user RTF groups.

    WPF emits embedded pictures as hex PNG, and escapes literal braces and
    backslashes. One brace scan finds the smallest paragraph group containing
    each unique marker. Removing that group also removes its blank paragraph.
    """
    positions = {}
    for number, token in enumerate(tokens):
        position = rtf.find(token)
        if position < 0 or rtf.find(token, position + len(token)) >= 0:
            raise ValueError('Could not locate the exported sheet boundaries.')
        positions[position] = number
    stack, found = [], {}
    index = 0
    while index < len(rtf):
        if index in positions:
            if not stack:
                raise ValueError('Invalid formatted sheet boundary.')
            stack[-1][1].append(positions[index])
        char = rtf[index]
        if char == '\\' and index + 1 < len(rtf) and rtf[index + 1] in '\\{}':
            index += 2
            continue
        if char == '{':
            stack.append([index, []])
        elif char == '}':
            if not stack:
                raise ValueError('Invalid exported RTF structure.')
            start, markers = stack.pop()
            if markers:
                group = rtf[start:index + 1]
                if len(markers) == 1 and Regex.Matches(group, r'\\par(?![a-zA-Z])').Count == 1:
                    found[markers[0]] = (start, index + 1)
                elif stack:
                    stack[-1][1].extend(markers)
        index += 1
    if stack or len(found) != len(tokens):
        raise ValueError('Could not preserve all exported sheet boundaries.')
    return found


def export_sheets_rtf(sheets, path):
    if not sheets:
        raise ValueError('There are no sheets to export.')
    combined = FlowDocument()
    combined.FontFamily = FontFamily('Calibri')
    combined.FontSize = 16.0
    combined.Foreground = Brushes.Black
    tokens = []
    scratch = RichTextBox()
    for sheet in sheets:
        _section_setup(sheet['orientation'])
        token = 'NDEVSHEET' + Guid.NewGuid().ToString('N')
        tokens.append(token)
        combined.Blocks.Add(Paragraph(Run(token)))
        load_document(scratch, sheet)
        blocks = scratch.Document.Blocks
        while blocks.FirstBlock is not None:
            block = blocks.FirstBlock
            blocks.Remove(block)
            combined.Blocks.Add(block)
    stream = MemoryStream()
    try:
        TextRange(combined.ContentStart, combined.ContentEnd).Save(stream, DataFormats.Rtf)
        rtf = Encoding.ASCII.GetString(stream.ToArray())
    finally:
        stream.Dispose()
    boundaries = _sheet_markers(rtf, tokens)
    for number in reversed(range(len(sheets))):
        start, end = boundaries[number]
        controls = (r'\sect' if number else '') + _section_setup(sheets[number]['orientation'])
        rtf = rtf[:start] + controls + rtf[end:]
    header = r'{\rtf1'
    if not rtf.startswith(header):
        raise ValueError('The note could not be exported as RTF.')
    # Default A4 setup, overridden by each section's own orientation above.
    defaults = r'\paperw11906\paperh16838\margl1134\margr1134\margt1134\margb1134'
    rtf = header + defaults + rtf[len(header):]
    File.WriteAllText(path, rtf, Encoding.ASCII)


def export_sheets_text(sheets):
    return u'\n\n'.join(u'{} | A4 {}\n{}'.format(
        sheet['name'], sheet['orientation'].capitalize(), sheet['body']) for sheet in sheets)
