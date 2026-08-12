"""Streamlit chat UI on top of the MCP server, driven by Gemini.

Run: streamlit run app.py
"""
import asyncio
import os
import sys

import streamlit as st
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from google import genai
from google.genai import types

load_dotenv()

FALLBACK_MODELS = [
    "gemini-flash-latest",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
]


def flatten_exception(exc: BaseException) -> str:
    """Unwrap ExceptionGroup/TaskGroup wrappers to find the real error message."""
    if isinstance(exc, BaseExceptionGroup):
        for sub in exc.exceptions:
            return flatten_exception(sub)
    return str(exc)


def generate_with_fallback(client, contents, config):
    """Try models in order, falling back to the next on any error (quota, retired model, etc)."""
    last_error = None
    for model in FALLBACK_MODELS:
        try:
            return client.models.generate_content(model=model, contents=contents, config=config), model
        except Exception as e:
            last_error = e
            continue
    raise RuntimeError(f"all fallback models failed: {flatten_exception(last_error)}")

st.set_page_config(page_title="MCP Agent", page_icon="🛰️")
st.title("MCP Agent")
st.caption("Weather, math, conference deadlines, arXiv paper search — via Gemini + MCP tools.")


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


async def run_turn(prompt: str, history: list[types.Content]) -> tuple[str, list[dict]]:
    """Send prompt through Gemini + MCP tool loop, return (final_text, tool_calls_log)."""
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    server_params = StdioServerParameters(command=sys.executable, args=["server.py"])
    tool_log = []

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            mcp_tools = (await session.list_tools()).tools
            gemini_tool = mcp_tools_to_gemini(mcp_tools)
            config = types.GenerateContentConfig(tools=[gemini_tool])

            contents = history + [types.Content(role="user", parts=[types.Part(text=prompt)])]

            while True:
                response, used_model = generate_with_fallback(client, contents, config)
                if used_model != FALLBACK_MODELS[0]:
                    tool_log.append({"name": "_fallback", "args": {}, "result": f"switched to {used_model}"})
                part = response.candidates[0].content.parts[0]
                contents.append(response.candidates[0].content)

                if not part.function_call:
                    return response.text, tool_log, contents

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

if prompt := st.chat_input("Ask about conferences, papers, weather, math..."):
    st.session_state.messages.append({"role": "user", "text": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("thinking..."):
            try:
                text, tool_log, new_history = asyncio.run(
                    run_turn(prompt, st.session_state.history)
                )
            except Exception as e:
                text, tool_log, new_history = f"Error: {flatten_exception(e)}", [], st.session_state.history
        st.markdown(text)
        for call in tool_log:
            with st.expander(f"🔧 {call['name']}({call['args']})"):
                st.code(call["result"], language="json")

    st.session_state.history = new_history
    st.session_state.messages.append({"role": "assistant", "text": text, "tool_log": tool_log})
