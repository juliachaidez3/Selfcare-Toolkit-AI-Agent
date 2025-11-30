import asyncio
from agents import Agent, Runner, gen_trace_id, trace
from agents.mcp import MCPServerStdio, MCPServer
from openai.types.responses import ResponseTextDeltaEvent
from dotenv import load_dotenv

load_dotenv()


async def main():
    async with MCPServerStdio(
        name="Self-Care MCP Server",
        params={
            "command": "uv",
            "args": ["run", "mcp-server/selfcare_mcp.py"],
        },
    ) as server:
        trace_id = gen_trace_id()
        with trace(workflow_name="Self-Care MCP Agent", trace_id=trace_id):
            print(f"View trace: https://platform.openai.com/traces/trace?trace_id={trace_id}\n")
            await run(server)


async def run(mcp_server: MCPServer):
    prompt_result = await mcp_server.get_prompt("system_prompt")
    instructions = prompt_result.messages[0].content.text

    agent = Agent(
        name="Self-Care Companion",
        instructions=instructions,
        mcp_servers=[mcp_server],
    )

    input_items = []

    print("=== Self-Care Agent ===")
    print("Type 'exit' to end the conversation")

    while True:
        user_input = input("\nUser: ").strip()
        input_items.append({"content": user_input, "role": "user"})

        if user_input.lower() in ["exit", "quit", "bye"]:
            print("\nTake care! 👋")
            break

        if not user_input:
            continue

        result = Runner.run_streamed(
            agent,
            input=input_items,
        )
        print("\nAgent: ", end="", flush=True)

        async for event in result.stream_events():
            if event.type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
                print(event.data.delta, end="", flush=True)
            elif event.type == "run_item_stream_event":
                if event.item.type == "tool_call_item":
                    tool_name = event.item.raw_item.name
                    print(f"\n-- Calling {tool_name}...")
                elif event.item.type == "tool_call_output_item":
                    input_items.append({"content": f"{event.item.output}", "role": "user"})
                    print("-- Tool call completed.")
                elif event.item.type == "message_output_item":
                    input_items.append({"content": f"{event.item.raw_item.content[0].text}", "role": "assistant"})
                    pass
                else:
                    pass

        print("\n")


if __name__ == "__main__":
    asyncio.run(main())
