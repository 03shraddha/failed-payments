"""
slack_mcp.py: MCP-based Slack alerting (demo).

Instead of calling the Slack SDK directly, this module:
  1. Spawns the official @modelcontextprotocol/server-slack as a local subprocess.
  2. Connects to it over stdio using the MCP Python SDK.
  3. Calls the Anthropic Claude API, giving it the MCP tools as available tools.
  4. Claude decides to call slack_post_message via the MCP tool - we execute that
     tool call against the live MCP server and return the result.

This is the "consuming an MCP" demo: the AI agent posts to Slack via tool use
rather than hardcoded SDK calls.

Requirements (add to requirements.txt):
    mcp>=1.0.0
    anthropic>=0.84.0   # 0.84+ ships native MCP helpers

Environment variables needed (already in .env):
    SLACK_BOT_TOKEN   : xoxb-... bot token
    SLACK_CHANNEL     : e.g. #payment-ops
    ANTHROPIC_API_KEY : your Claude API key
"""

import asyncio
import json
import logging
import os

import anthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from config import SLACK_BOT_TOKEN, SLACK_CHANNEL

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers (same masking logic as the original slack.py)
# ---------------------------------------------------------------------------

def _mask_phone(phone: str | None) -> str:
    if not phone:
        return "N/A"
    digits = phone.replace("+", "").replace(" ", "").replace("-", "")
    return f"****{digits[-4:]}" if len(digits) >= 4 else "****"


def _mask_email(email: str | None) -> str:
    if not email or "@" not in email:
        return "N/A"
    local, domain = email.split("@", 1)
    return f"{local[0]}***@{domain}"


# ---------------------------------------------------------------------------
# Build the natural-language prompt that Claude will act on
# ---------------------------------------------------------------------------

def _build_prompt(
    payment_id: str,
    order_id: str,
    amount: float,
    reason: str,
    phone: str | None,
    email: str | None,
    method: str,
    link: str,
    sms_sent: bool,
    email_sent: bool,
) -> str:
    sms_status   = "SMS sent"   if sms_sent   else "SMS NOT sent"
    email_status = "Email sent" if email_sent else "Email NOT sent"

    return f"""
Post a Slack alert to the channel {SLACK_CHANNEL} about a failed payment.

Details:
- Payment ID : {payment_id}
- Order ID   : {order_id}
- Amount     : ₹{amount:.2f}
- Method     : {method.upper()}
- Reason     : {reason}
- Phone      : {_mask_phone(phone)}
- Email      : {_mask_email(email)}
- Recovery   : {link}
- Actions    : {sms_status}, {email_status}

Format the message clearly so the payments-ops team can act on it immediately.
Use the slack_post_message tool to post to channel {SLACK_CHANNEL}.
""".strip()


# ---------------------------------------------------------------------------
# Core: connect to MCP server, give tools to Claude, execute tool calls
# ---------------------------------------------------------------------------

async def _post_via_mcp(prompt: str) -> None:
    """
    Spawn the Slack MCP server, list its tools, call Claude with those tools,
    then execute whatever tool call Claude returns against the MCP server.
    """

    # --- 1. Start the Slack MCP server as a local subprocess via stdio -----
    #
    #  npx -y @modelcontextprotocol/server-slack
    #  The server reads SLACK_BOT_TOKEN from the environment automatically.
    #
    server_params = StdioServerParameters(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-slack"],
        env={
            **os.environ,           # inherit the full environment
            "SLACK_BOT_TOKEN": SLACK_BOT_TOKEN,
        },
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:

            # --- 2. Handshake & discover tools --------------------------------
            await session.initialize()

            tools_response = await session.list_tools()
            mcp_tools = tools_response.tools  # list[mcp.types.Tool]

            logger.info(
                "Slack MCP server ready. Tools available: %s",
                [t.name for t in mcp_tools],
            )

            # --- 3. Convert MCP tool schemas → Anthropic tool format ---------
            #
            # Anthropic tool schema:
            #   { "name": str, "description": str,
            #     "input_schema": { "type": "object", "properties": {...} } }
            #
            # MCP tool schema:
            #   tool.name, tool.description, tool.inputSchema (already a dict)
            #
            anthropic_tools = [
                {
                    "name": t.name,
                    "description": t.description or "",
                    "input_schema": t.inputSchema,  # MCP already uses JSON Schema
                }
                for t in mcp_tools
            ]

            # --- 4. Call Claude with the MCP tools available -----------------
            # Use AsyncAnthropic so the event loop isn't blocked during the API call.
            client = anthropic.AsyncAnthropic()  # reads ANTHROPIC_API_KEY from env

            response = await client.messages.create(
                model="claude-3-5-haiku-20241022",   # fast + cheap for alerts
                max_tokens=1024,
                tools=anthropic_tools,
                messages=[{"role": "user", "content": prompt}],
            )

            logger.info("Claude stop_reason: %s", response.stop_reason)

            # --- 5. Execute the tool call(s) Claude requested ----------------
            #
            # Claude responds with stop_reason="tool_use" when it wants to call
            # a tool. We find those content blocks and execute them via the MCP
            # session.
            #
            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_name  = block.name
                tool_input = block.input   # dict already

                logger.info(
                    "Claude calling MCP tool '%s' with args: %s",
                    tool_name,
                    json.dumps(tool_input, ensure_ascii=False),
                )

                # Execute the tool call on the live MCP server
                result = await session.call_tool(tool_name, arguments=tool_input)

                # result.content is a list of TextContent / ImageContent blocks
                for content_block in result.content:
                    if hasattr(content_block, "text"):
                        logger.info("MCP tool result: %s", content_block.text)

            logger.info("Slack alert posted via MCP for prompt snippet: %.60s…", prompt)


# ---------------------------------------------------------------------------
# Public async entry point (drop-in replacement for actions/slack.py)
# ---------------------------------------------------------------------------

async def post_slack(
    payment_id: str,
    order_id: str,
    amount: float,
    reason: str,
    phone: str | None,
    email: str | None,
    method: str,
    link: str,
    sms_sent: bool = True,
    email_sent: bool = True,
) -> None:
    """
    Async entry point: same signature as the original post_slack() so it can
    be swapped in without touching main.py.

    Flow:
        build prompt → spawn MCP server → list tools → call Claude →
        Claude picks slack_post_message → execute via MCP → Slack notified
    """
    prompt = _build_prompt(
        payment_id, order_id, amount, reason,
        phone, email, method, link,
        sms_sent, email_sent,
    )
    await _post_via_mcp(prompt)
