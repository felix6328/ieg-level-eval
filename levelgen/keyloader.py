import re
def load_key(path="/workspace/video-workflow/.env"):
    with open(path) as f:
        for line in f:
            m = re.match(r'\s*(?:export\s+)?SILICONFLOW_API_KEY\s*=\s*(.*)$', line)
            if m:
                return m.group(1).strip().strip('"').strip("'")
    raise SystemExit("SILICONFLOW_API_KEY not found")
