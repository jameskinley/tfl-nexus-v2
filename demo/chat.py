import json
from contextlib import AsyncExitStack
from logging import getLogger

from mcp import ClientSession
from mcp.client.sse import sse_client
from openai import AsyncOpenAI

try:
    from .cfg import BASE_URL, API_KEY, MODEL, MCP_SSE_URL
except ImportError:
    from cfg import BASE_URL, API_KEY, MODEL, MCP_SSE_URL


class Chat:
    def __init__(self):
        self.history: list = []
        self.logger = getLogger(__name__)
        self.client = AsyncOpenAI(base_url=BASE_URL, api_key=API_KEY)
        self._exit_stack = AsyncExitStack()
        self._session: ClientSession | None = None
        self._tools: list = []

    async def _ensure_session(self):
        """Lazily connect to the MCP server over SSE."""
        if self._session is not None:
            return
        transport = await self._exit_stack.enter_async_context(sse_client(MCP_SSE_URL))
        read, write = transport
        self._session = await self._exit_stack.enter_async_context(
            ClientSession(read, write)
        )
        await self._session.initialize()
        response = await self._session.list_tools()
        self._tools = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema,
                },
            }
            for tool in response.tools
        ]
        self.logger.info("MCP tools available: %s", [t["function"]["name"] for t in self._tools])

    async def message(self, content: str) -> str:
        try:
            await self._ensure_session()
            self.history.append({"role": "user", "content": content})

            response = await self.client.chat.completions.create(
                model=MODEL,
                messages=self.history,
                tools=self._tools or None,
                tool_choice="auto" if self._tools else None,
            )

            # Agentic loop — keep going until no more tool calls
            while response.choices[0].finish_reason == "tool_calls":
                msg = response.choices[0].message
                self.history.append(msg)  # assistant turn with tool_calls

                for tc in msg.tool_calls or []:
                    self.logger.info("Calling MCP tool: %s args=%s", tc.function.name, tc.function.arguments)
                    result = await self._session.call_tool(  # type: ignore[union-attr]
                        tc.function.name,
                        json.loads(tc.function.arguments),
                    )
                    tool_content = (
                        result.content[0].text
                        if result.content and hasattr(result.content[0], "text")
                        else json.dumps(result.content)
                    )
                    self.history.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": tool_content,
                    })

                response = await self.client.chat.completions.create(
                    model=MODEL,
                    messages=self.history,
                    tools=self._tools or None,
                    tool_choice="auto" if self._tools else None,
                )

            reply = response.choices[0].message
            self.history.append({"role": "assistant", "content": reply.content})
            return reply.content or ""

        except Exception as exc:
            self.logger.exception("Error in Chat.message")
            raise exc

    async def close(self):
        await self._exit_stack.aclose()