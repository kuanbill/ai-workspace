# AI Collaboration Platform for Windows

Windows 桌面版 AI 協作平台，目標是在本機提供一個可管理多個 AI 供應商、驗證 API、查詢可用模型並進行對話協作的工作台。

## Current Scope

- Windows 桌面 GUI，使用 `CustomTkinter`
- 支援多供應商設定與切換
- 支援 API 驗證與模型查詢
- 支援對話紀錄與使用者管理
- 使用本機 SQLite 儲存設定與歷史資料
- 支援知識文件匯入的基礎框架

## Supported Providers

- OpenAI
- Azure OpenAI
- Anthropic
- Google Gemini
- Ollama
- Custom OpenAI-compatible endpoint

## Main Flow

1. 在「系統設定」新增 AI 供應商
2. 輸入 `Base URL`、`API Key`、模型或部署名稱
3. 點擊「驗證 API」確認連線可用
4. 點擊「查詢可用模型」載入供應商可用模型
5. 設定目前對話使用的供應商
6. 在「AI 對話」頁面開始協作

## Quick Start

```bash
pip install -r requirements.txt
python app.py
```

## Build EXE

```bash
pyinstaller AI-Platform.spec
```

輸出檔預設會在 `dist/`。

### Bundled Tools

- `AI-Platform.spec` 會自動打包 `skills/`、`vendor/`，以及存在時的 `tool_runtime/pandoc/`
- 若要把 `pandoc` 一起打進 EXE，請先把 `pandoc.exe` 放到 `tool_runtime/pandoc/` 底下
- `LibreOffice` 預設不隨專案一起打包，建議安裝到使用者系統，或在 app 的「系統環境設定」手動指定 `soffice.exe`

### Office Dependency Strategy

- `pandoc`：可隨 app 一起打包，執行時會優先搜尋使用者指定路徑，再搜尋系統 PATH、標準安裝目錄與 `tool_runtime/`
- `LibreOffice / soffice`：不預設打包，執行時會優先搜尋使用者指定路徑，再搜尋系統 PATH 與常見安裝目錄
- `pdftoppm`：可使用系統安裝的 Poppler，或在 app 的「系統環境設定」手動指定 `pdftoppm.exe`

## Project Files

- `app.py`: 主程式與 UI
- `AI-Platform.spec`: PyInstaller 打包設定
- `data/`: 本機 SQLite 資料
- `knowledge_base/`: 使用者匯入的知識文件

## Security Note

目前版本會把 API Key 儲存在本機 SQLite 資料庫。這適合本機開發與個人使用，但如果要正式發布給其他使用者，建議下一步改成：

- Windows Credential Manager
- 加密後的本機設定檔
- 使用者層級的金鑰保護機制

## Roadmap

- AI 工具呼叫與工作流執行
- 更完整的知識庫檢索
- API Key 安全儲存
- 模型能力標示與預設路由
- 安裝包與自動更新流程
