import json
S = []
def add(i, install, code): S.append({"i": i, "install": install, "code": code})

MCP_SERVER_ROUNDTRIP = r'''
import asyncio, socket, threading, time
import httpx, uvicorn
from mcp.server.mcpserver import MCPServer
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
srv = MCPServer("t")
@srv.tool()
def ping() -> str:
    return "pong"
app = srv.streamable_http_app()
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
t = threading.Thread(target=server.run, daemon=True); t.start()
for _ in range(100):
    if server.started: break
    time.sleep(0.1)
async def main():
    # the repository's form: a legacy httpx.AsyncClient passed as http_client
    async with httpx.AsyncClient(timeout=30.0) as http_client:
        async with streamable_http_client(f"http://127.0.0.1:{port}/mcp", http_client=http_client) as (r, w):
            async with ClientSession(r, w) as session:
                await session.initialize()
                tools = [t.name for t in (await session.list_tools()).tools]
                assert tools == ["ping"], tools
                print("roundtrip ok", tools)
asyncio.run(asyncio.wait_for(main(), 60))
server.should_exit = True
'''
add(0, ["mcp==2.2.0", "httpx", "uvicorn"], MCP_SERVER_ROUNDTRIP)
add(1, ["click==8.5.0"], "import click\nprint(click.utils.make_default_short_help('Run the orchestrator and do several more things', 45))\n")
add(5, ["mcp==2.0.0"], "import inspect\nfrom mcp.client.session import ClientSession\ninspect.signature(ClientSession.list_resources).bind(object())\ninspect.signature(ClientSession.__init__).bind(object(), 'r', 'w')\nprint('bind ok')\n")
add(4, ["mcp==2.0.0"], "import inspect\nfrom mcp.client.session import ClientSession\ninspect.signature(ClientSession.__init__).bind(object(), 'r', 'w')\nprint('bind ok')\n")
add(7, ["openai==3.37.0", "httpx"], "import httpx\nfrom openai import AsyncOpenAI\nc = AsyncOpenAI(api_key='sk-test', base_url='http://127.0.0.1:9/v1', http_client=httpx.AsyncClient(trust_env=True))\nprint(type(c._client))\n")
add(10, ["langsmith==0.14.12"], "import uuid\nfrom langsmith import Client\nc = Client(api_key='lsv2_test', api_url='http://127.0.0.1:9')\ng = c.list_runs(project_id=uuid.uuid4(), is_root=True)\nprint(type(g))\n")
add(12, ["mcp==2.1.1"], "import inspect\nfrom mcp.client.session import ClientSession\ninspect.signature(ClientSession.list_tools).bind(object())\nprint('bind ok')\n")
add(18, ["websockets==17.2"], r'''
import asyncio, logging
from websockets.asyncio.server import serve
async def handler(ws):
    await ws.close()
def discovery(connection, request):
    return None
async def main():
    async with serve(handler, "127.0.0.1", 0, process_request=discovery, logger=logging.getLogger("x"), max_size=None, ping_interval=None) as server:
        print("async with ok", server.sockets[0].getsockname()[1] > 0)
    server2 = await serve(handler, "127.0.0.1", 0)
    print("await ok", server2.sockets[0].getsockname()[1] > 0)
    server2.close(); await server2.wait_closed()
asyncio.run(main())
''')
add(22, ["vercel==0.12.0"], "from vercel.sandbox import Sandbox, SandboxStatus, WriteFile\nprint('import ok', Sandbox, SandboxStatus, WriteFile)\n")
add(23, ["apprise==2.0.1"], "import apprise\na = apprise.Apprise()\nprint('add ->', a.add('json://localhost'))\n")
add(31, ["mcp==2.2.0"], "import inspect\nfrom mcp.client.session import ClientSession\ninspect.signature(ClientSession.__init__).bind(object(), 'r', 'w', read_timeout_seconds=5.0)\nprint('bind ok')\n")
add(32, ["mcp==2.2.0"], "import inspect\nfrom mcp.server.mcpserver import MCPServer\nprint(inspect.signature(MCPServer.call_tool))\ninspect.signature(MCPServer.call_tool).bind(object(), 'media_upload_link', {})\nprint('bind ok')\n")
add(52, ["mcp==2.1.1"], "import inspect\nfrom mcp.client.session import ClientSession\ninspect.signature(ClientSession.list_prompts).bind(object())\nprint('bind ok')\n")
add(53, ["plotly==7.1.0"], "from plotly.graph_objects import Bar\nb = Bar(x=[1, 2], y=[3, 4], marker=dict(color='#3465a4'), name='label')\nprint('ok', b.type)\n")
add(54, ["plotly==7.1.0"], "from plotly.graph_objects import Scatter3d\ns = Scatter3d(x=[1], y=[2], z=[3])\nprint('ok', s.type)\n")
add(58, ["mcp==2.1.1"], "from mcp.server.mcpserver import MCPServer as _Server, Context\nimport inspect\nprint('import ok', 'version' in inspect.signature(_Server).parameters)\n")
add(59, ["mcp==2.1.1"], "import inspect\nfrom mcp.server.mcpserver import MCPServer\ns = MCPServer(name='autoclip', instructions='x')\nprint(inspect.signature(s.call_tool))\ninspect.signature(s.call_tool).bind('name', {}, None)\nprint('bind ok')\n")
json.dump(S, open("since_cutoff_runs/realworld2/audit/snippets.json", "w", encoding="utf-8"), indent=1)
print(len(S))
