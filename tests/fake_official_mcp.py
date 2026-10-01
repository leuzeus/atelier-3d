"""Synthetic stdio provider; never launches ComfyUI or produces real assets."""
import json
import os
import sys

for line in sys.stdin:
    request=json.loads(line)
    if "id" not in request: continue
    method=request["method"]; args=request.get("params",{})
    if method=="initialize":
        result={"protocolVersion":"2025-06-18","capabilities":{"tools":{}},"serverInfo":{"name":"fake-official","version":"0"}}
    elif method=="tools/list":
        if args.get("cursor"):
            result={"tools":[{"name":"text-result"},{"name":"error-result"},{"name":"elicitation"}]}
        else:
            result={"tools":[{"name":"probe"}],"nextCursor":"page-2"}
    elif method=="tools/call":
        name=args["name"]
        if name=="probe":
            result={"structuredContent":{"result":{"url":os.environ.get("COMFY_LOCAL_URL"),
                "cli":os.environ.get("COMFY_BIN"),"project":os.environ.get("COMFY_PROJECT"),
                "remote_removed":"COMFYUI_URL" not in os.environ,
                "key_removed":"COMFY_API_KEY" not in os.environ}}}
        elif name=="text-result":
            result={"content":[{"type":"text","text":json.dumps({"answer":42})}]}
        elif name=="error-result":
            result={"isError":True,"content":[{"type":"text","text":"synthetic failure"}]}
        elif name=="elicitation":
            print(json.dumps({"jsonrpc":"2.0","id":"provider-1","method":"elicitation/create","params":{}}),flush=True)
            denial=json.loads(sys.stdin.readline())
            result={"structuredContent":{"rejected":denial.get("error",{}).get("code")==-32601}}
        else: raise AssertionError(name)
    else: result={}
    print(json.dumps({"jsonrpc":"2.0","id":request["id"],"result":result}),flush=True)
