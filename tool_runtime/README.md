Place optional bundled command-line tools here for packaging.

Recommended layout:

- `tool_runtime/pandoc/.../pandoc.exe`

Build behavior:

- `AI-Platform.spec` includes `tool_runtime/pandoc` automatically when present.
- `office_tools.py` also searches this directory at runtime.

LibreOffice strategy:

- Do not bundle LibreOffice in this repository by default.
- Install LibreOffice on the target machine, or let the user select `soffice.exe`
  in "系統環境設定".
