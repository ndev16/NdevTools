# NdevTools Handy

This panel belongs in `Ndevtools.extension/NdevTools.tab/Handy.panel`.
Add `Handy` to the tab's `bundle.yaml` layout and reload pyRevit.

## Notes

Click **Notes** to open a personal notebook alongside Revit. Use **New note**
(Ctrl+N), enter a title and content, then **Save** (Ctrl+S). Edits also autosave
after 1.2 seconds of inactivity and before changing notes or closing the window.
Existing plain-text notes open without modification and gain rich content only
when saved through the upgraded editor.

Select text and use the toolbar for font family and size (points), bold, italic,
underline, alignment, bullets and numbering. **Text color**, **Highlight**,
**Clear highlight** and **Page color** allow custom colors. Color buttons open an
inline WPF palette with swatches, RGB sliders and a #RRGGBB field. Click **Apply
color** to commit, or click outside/Cancel/Escape to leave the note unchanged.
The palette does not use the Windows Forms color dialog. Standard Ctrl+B/I/U,
Ctrl+Z/Y and rich-text paste are supported. Font sizes from 1 to 200 points are
accepted; press Enter after entering a custom size.

Use **Insert image** for a local file or **Paste image** for a copied screenshot.
Ctrl+V also accepts bitmap clipboard content. Click an embedded image, enter its
width and click **Resize**; press Delete to remove a selected image. Large images
are downscaled to a maximum width of 1800 pixels for notebook storage. Images are
embedded in the note and do not depend on the original file afterward.

**Export** offers Word-compatible RTF (text formatting and images) or UTF-8 plain
text. Plain-text export omits images and formatting. RTF may not preserve the
editor's page background color. Search continues to match titles and saved text.
Reopening the button activates its existing window. When upgrading from the old
plain-text editor, the old window closes through its normal save/close path.

Notes are personal files stored under `%APPDATA%/NdevTools/Handy/Notes`.
They are not stored in the Revit model. Each note has its own UTF-8 JSON file. Rich notes use schema version 2,
with a base64 WPF XamlPackage holding text formatting and image bytes; version 1
plain-text notes remain supported. The plain-text body remains available for search.
Updates replace files atomically and retain the previous saved version in
`.json.bak`. **Delete** moves the saved note into the `Deleted` subfolder. To
recover it, restore its original `<id>.json` filename in the Notes folder.
Copy a `.json.bak` file back to its matching `.json` path to recover that version.
Close Notes before manually restoring files.

If a note was changed in another Revit session, Save offers to preserve your
edits as a new note. Unreadable note files are reported and left untouched.

## Useful Links

**Image to Text** opens https://www.imagetotext.info/ and **Convert Case** opens
https://convertcase.net/. Each site has its own embedded browser view, so
switching tools keeps the other page alive. Back, Forward and Reload act on the
selected page. The modeless window can remain open while you work in Revit.

The browser uses Microsoft WebView2 components from the currently running Revit
installation, with a separate profile in
`%LOCALAPPDATA%/NdevTools/Handy/WebView2/<Revit installation name>`.
It requires the Microsoft Edge WebView2 Runtime and an internet connection.
If initialization fails or a site restricts embedded browsers, use **Open in
browser**. Web uploads, downloads, sign-ins and conversions remain controlled
by the user on the selected website. No model data is sent automatically and
no Revit host objects are exposed to web content.

## Compatibility and verification

WPF / pyRevit / IronPython 2.7, Revit 2022 or later. Embedded browsing requires
the WebView2 SDK in the active Revit installation; Notes does not depend on it.
The 2023 Dynamo and 2024+ root installation SDK locations are supported.
Neither button opens a Revit document transaction.

Created by Nataraj Devaraj.

## Help, developer footer, and BIM humor

Both tools use FramePilot-style logo/title headers, a top Help button, and a
creator footer with a cyan **★ Star NdevTools on GitHub** button. Help opens a
separate owned window with tool-specific instructions and both profile links:

- GitHub: https://github.com/ndev16/NdevTools
- LinkedIn: https://www.linkedin.com/in/nataraj016/

The humor strip is On by default. Toggle **BIM Humor On/Off** to show or hide
jokes, and use **Next Joke** to change the joke. Each tool remembers its own
humor preference in the `ndev_handy_ui` section of the pyRevit configuration.
No background timer runs for jokes. Status messages remain above the footer.

Both ribbon bundles retain their 20 locales and now describe Help, footer links,
and humor controls in those locales.

## Writing space and A4 exports

Use **Fill window** to fill the available width and height, with a compact header and a
single wrapping formatting toolbar. Drag the sidebar divider to resize the note
list or choose Hide notes to use the full window for writing. Show notes restores
the list at its previous width. The editor uses small 12-pixel inset margins.
RTF exports retain each sheet's portrait or landscape A4 layout with 20 mm print margins.
Text, images, formatting, autosave, Help and footer controls remain available.

## Multiple sheets and orientation

Use **+ Add sheet** to append a sheet inside the current note, and the sheet
dropdown to switch. Each sheet has its own **Portrait** or **Landscape** A4
orientation. New sheets inherit the current orientation. Sheet content includes
text, formatting, colors and embedded images. The active sheet is remembered.
Saving and autosave keep all sheets in one version 3 note JSON file; search uses
text from every sheet. Existing version 1 and 2 notes open as one portrait sheet
and are upgraded only when saved, retaining the previous saved file as a backup.
RTF exports all sheets in order with an A4 section and 20 mm margins per sheet.
Each sheet starts on a new page; long sheets can span further printed pages.
Plain-text export includes every sheet with its name and orientation.

## Visible orientation and layout stability

Portrait and Landscape now change the A4 paper width and height in the editor.
Use **Fill window** for the full writing area. Changing orientation returns to
A4 page view so the selected layout is visible. Both modes keep the same content.
Layout updates are queued once after a document loads; the editor no longer
modifies the document from the global WPF LayoutUpdated callback.
The printed GitHub/LinkedIn URLs are removed from both translated YAML tooltips;
the Help links and GitHub footer button remain available.
