# OpenClaw Office Add-in (Excel + Word)

This add-in connects Excel/Word to your local Awarenet proxy at `http://127.0.0.1:11435`.

## Start the add-in server

```powershell
cd C:\AI_Assistant\office-addin
powershell -NoExit -ExecutionPolicy Bypass -File .\serve_addin.ps1
```

## Sideload (Windows Desktop)

### Excel
1. Open Excel.
2. File → Options → Trust Center → Trust Center Settings → Trusted Add-in Catalogs.
3. Add a shared folder and point it to `C:\AI_Assistant\office-addin`.
4. Close and reopen Excel.
5. Insert → My Add-ins → Shared Folder → OpenClaw Assistant.

### Word
Repeat the same steps in Word.

## Custom function
Use in Excel:
```
=GPT("Summarize this", A1:A5)
```

## Task pane features
- Chat with your local model
- Run prompts on selected Excel range
- Summarize or rewrite selected Word text

## Endpoint settings
Open the task pane and change endpoint/model if needed. Settings are saved per document.
