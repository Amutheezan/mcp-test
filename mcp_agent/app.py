"""Streamlit chat UI on top of the MCP server, driven by Gemini.

Run: streamlit run mcp_agent/app.py
"""
import asyncio
import os
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from google import genai
from google.genai import types

import storage

load_dotenv()

ALL_MODELS = [
    "gemini-flash-latest",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
]

QUOTA_ERROR_MARKERS = ("quota", "resource_exhausted", "429", "rate limit")


def flatten_exception(exc: BaseException) -> str:
    """Unwrap ExceptionGroup/TaskGroup wrappers to find the real error message."""
    if isinstance(exc, BaseExceptionGroup):
        for sub in exc.exceptions:
            return flatten_exception(sub)
    return str(exc)


def is_quota_error(exc: BaseException) -> bool:
    msg = flatten_exception(exc).lower()
    return any(marker in msg for marker in QUOTA_ERROR_MARKERS)


def generate_with_fallback(client, contents, config, candidate_models: list[str]):
    """Try models in order, falling back to the next on any error (quota, retired model, etc)."""
    last_error = None
    for model in candidate_models:
        try:
            return client.models.generate_content(model=model, contents=contents, config=config), model
        except Exception as e:
            if is_quota_error(e):
                storage.mark_quota_exceeded(model)
            last_error = e
            continue
    raise RuntimeError(f"all fallback models failed: {flatten_exception(last_error)}")

st.set_page_config(page_title="Amutheezan Assistant", page_icon="🛰️")
st.title("Amutheezan Assistant")
st.caption("AI and Security Research")


def mcp_tools_to_gemini(mcp_tools) -> types.Tool:
    declarations = [
        types.FunctionDeclaration(
            name=t.name,
            description=t.description or "",
            parameters=t.input_schema,
        )
        for t in mcp_tools
    ]
    return types.Tool(function_declarations=declarations)


async def run_turn(
    prompt: str,
    history: list[types.Content],
    api_key: str,
    candidate_models: list[str],
    interests: list[str],
    memory: str,
    recent_searches: list[str],
) -> tuple[str, list[dict], list, str]:
    """Send prompt through Gemini + MCP tool loop, return (final_text, tool_calls_log, history, model_used)."""
    client = genai.Client(api_key=api_key)
    server_params = StdioServerParameters(command=sys.executable, args=[str(Path(__file__).resolve().parent / "server.py")])
    tool_log = []

    context_lines = []
    if interests:
        context_lines.append("User interests: " + ", ".join(interests))
    if memory.strip():
        context_lines.append("Notes to remember about the user: " + memory.strip())
    if recent_searches:
        context_lines.append("User's recent search history (most recent first): " + " | ".join(recent_searches))
    system_prefix = "\n".join(context_lines)

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            mcp_tools = (await session.list_tools()).tools
            gemini_tool = mcp_tools_to_gemini(mcp_tools)
            config = types.GenerateContentConfig(
                tools=[gemini_tool],
                system_instruction=system_prefix or None,
            )

            contents = history + [types.Content(role="user", parts=[types.Part(text=prompt)])]

            used_model = None
            while True:
                response, used_model = generate_with_fallback(client, contents, config, candidate_models)
                part = response.candidates[0].content.parts[0]
                contents.append(response.candidates[0].content)

                if not part.function_call:
                    return response.text, tool_log, contents, used_model

                fc = part.function_call
                args = dict(fc.args)
                result = await session.call_tool(fc.name, args)
                tool_output = result.content[0].text
                tool_log.append({"name": fc.name, "args": args, "result": tool_output})

                contents.append(
                    types.Content(
                        role="user",
                        parts=[
                            types.Part(
                                function_response=types.FunctionResponse(
                                    name=fc.name,
                                    response={"result": tool_output},
                                )
                            )
                        ],
                    )
                )


# ---- sidebar: interests, memory, API key, model picker, search history ----

with st.sidebar:
    st.header("Settings")

    with st.expander("🔑 API key", expanded=not (storage.get_api_key() or os.environ.get("GEMINI_API_KEY"))):
        key_input = st.text_input("Gemini API key", type="password", value=storage.get_api_key() or "")
        if st.button("Save API key"):
            storage.set_api_key(key_input)
            st.success("Saved.")

    available_models = storage.get_available_models(ALL_MODELS)
    cooldowns = storage.get_model_cooldowns(ALL_MODELS)
    saved_model = storage.get_selected_model()
    model_options = available_models or ALL_MODELS  # never leave the picker empty
    default_index = model_options.index(saved_model) if saved_model in model_options else 0
    chosen_model = st.selectbox("Model", model_options, index=default_index)
    if chosen_model != saved_model:
        storage.set_selected_model(chosen_model)
    if cooldowns:
        blocked_list = ", ".join(f"{m} ({int(s // 60)}m)" for m, s in cooldowns.items())
        st.caption(f"⏳ quota cooldown: {blocked_list}")

    st.divider()
    st.subheader("Interests")
    new_interest = st.text_input("Add interest", key="new_interest_input")
    if st.button("Add") and new_interest.strip():
        storage.add_interest(new_interest)
        st.rerun()
    interests = storage.list_interests()
    for it in interests:
        cols = st.columns([5, 1])
        cols[0].write(it["text"])
        if cols[1].button("✕", key=f"del_interest_{it['id']}"):
            storage.delete_interest(it["id"])
            st.rerun()

    st.divider()
    st.subheader("Memory")
    memory_text = st.text_area("Notes the agent should remember", value=storage.get_memory(), height=100)
    if st.button("Save memory"):
        storage.set_memory(memory_text)
        st.success("Saved.")

    st.divider()
    st.subheader("Search history")
    history_rows = storage.list_search_history()
    if st.button("Clear history"):
        storage.clear_search_history()
        st.rerun()
    for row in history_rows:
        label = row["query"] if len(row["query"]) <= 60 else row["query"][:57] + "..."
        st.caption(f"{label}  ·  {row['model_used'] or '?'}")


if "messages" not in st.session_state:
    st.session_state.messages = []  # [{"role": "user"/"assistant", "text": str, "tool_log": [...]}]
if "history" not in st.session_state:
    st.session_state.history = []  # list[types.Content] for Gemini context

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["text"])
        for call in msg.get("tool_log", []):
            with st.expander(f"🔧 {call['name']}({call['args']})"):
                st.code(call["result"], language="json")

if prompt := st.chat_input("Ask about conferences ..."):
    st.session_state.messages.append({"role": "user", "text": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    active_api_key = storage.get_api_key() or os.environ.get("GEMINI_API_KEY")
    saved_model = storage.get_selected_model()
    candidate_models = storage.get_available_models(ALL_MODELS)
    if saved_model and saved_model in candidate_models:
        candidate_models = [saved_model] + [m for m in candidate_models if m != saved_model]
    if not candidate_models:
        candidate_models = ALL_MODELS

    used_model = None
    with st.chat_message("assistant"):
        with st.spinner("thinking..."):
            if not active_api_key:
                text, tool_log, new_history = "Error: no Gemini API key set. Add one in the sidebar.", [], st.session_state.history
            else:
                try:
                    text, tool_log, new_history, used_model = asyncio.run(
                        run_turn(
                            prompt,
                            st.session_state.history,
                            active_api_key,
                            candidate_models,
                            [it["text"] for it in storage.list_interests()],
                            storage.get_memory(),
                            [row["query"] for row in storage.list_search_history(limit=10)],
                        )
                    )
                except Exception as e:
                    text, tool_log, new_history = f"Error: {flatten_exception(e)}", [], st.session_state.history
        st.markdown(text)
        for call in tool_log:
            with st.expander(f"🔧 {call['name']}({call['args']})"):
                st.code(call["result"], language="json")

    storage.add_search(prompt, used_model)
    st.session_state.history = new_history
    st.session_state.messages.append({"role": "assistant", "text": text, "tool_log": tool_log})