# AI Collaboration Platform - Windows Desktop

Windows AI 協作平台 - 桌面應用程式

## 功能

1. **後端管理**: API 供應商設定（OpenAI/Anthropic/Ollama/Azure）、模型選擇
2. **GUI**: AI 對話、使用者資料、系統設定
3. **本地資料庫**: SQLite (AI 可操作)
4. **知識庫**: 使用者上傳文件建立知識庫
5. **Tools/Skills**: AI 可呼叫的功能

## 安裝

```bash
pip install -r requirements.txt
```

## 執行與建置

```bash
python app.py
```

建置 exe:
```bash
pyinstaller --onefile --noconsole --icon=icon.ico app.py
```