import json
path = "/Users/yunwesth/.claude/projects/-Users-yunwesth-PitchClockResearch/d302e59b-936c-4eed-a2e2-cc46cf9859d5.jsonl"
with open(path) as f:
    for i, line in enumerate(f):
        try:
            obj = json.loads(line)
        except Exception:
            continue
        msg = obj.get("message", {})
        role = msg.get("role")
        content = msg.get("content")
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            texts = []
            for c in content:
                if isinstance(c, dict):
                    if c.get("type") == "text":
                        texts.append(c.get("text",""))
                    elif c.get("type") == "tool_use":
                        texts.append(f"[TOOL_USE {c.get('name')} input={json.dumps(c.get('input'))[:300]}]")
                    elif c.get("type") == "tool_result":
                        cc = c.get("content")
                        if isinstance(cc, list):
                            for x in cc:
                                if isinstance(x, dict) and x.get("type")=="text":
                                    texts.append(f"[TOOL_RESULT {x.get('text','')[:500]}]")
                        elif isinstance(cc, str):
                            texts.append(f"[TOOL_RESULT {cc[:500]}]")
            text = "\n".join(texts)
        else:
            text = ""
        if text.strip():
            print(f"--- line {i} role={role} ---")
            print(text[:2000])
            print()
