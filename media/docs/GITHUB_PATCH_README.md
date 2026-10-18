# NdevTools repository update

The current checkout contains the complete extension contents, not a nested
PATCH_FILES wrapper. The runtime tab has **12 commands** across five panels.
Keep `extension.json`, `startup.py` and `NdevTools.tab` at the extension root.

The October 19 sync brings the current testing tools and resources into the
repository, updates the ribbon catalog and documentation, and refreshes the
ribbon and 20-language images. The old `Create walls.pushbutton` bundle is
superseded by `Create walls and opening.pushbutton`; install only the current
bundle to avoid duplicate Wall Tracing buttons.

Review the local Git diff before committing. This update does not automatically
commit, push, or publish. Use a separate test project to verify runtime behavior
before a public release. See [installation](GITHUB_INSTALL.md),
[translation scope](../../BUNDLE_TRANSLATIONS.md), and [changelog](../../CHANGELOG.md).
