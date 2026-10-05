# mcp-test

Two small, independent projects.

```
mcp_agent/   Streamlit chat UI + MCP server (conference tools), driven by Gemini
dongle/      Desktop pet: animated character hanging from the top-right of the screen (PySide6)
notebooks/   Experiments (vLLM tokens/sec benchmark)
```

## mcp_agent
```
pip install -r mcp_agent/requirements.txt
echo GEMINI_API_KEY=... > .env        # or enter it in the UI
streamlit run mcp_agent/app.py
```

## dongle
```
pip install -r dongle/requirements.txt
python dongle/dongle.py               # or dongle\start_dongle.bat
```
Right-click the character for animations, customization, `Use Gemini body`
(full-body anime sprites from `dongle/sprites/`) and "Start with Windows".

Regenerate the character sheet with `python dongle/generate_sheet.py`
(prompt in `dongle/prompts/`, needs a Gemini key with image-model quota and a
reference photo at `input_photos/photo.jpg`, which is git-ignored).
