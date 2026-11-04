"""样例：硬编码密钥 + 长行。"""
import os


def send(payload, token="sk-live-9f2c1a77d0"):
    headers = {"Authorization": token, "Content-Type": "application/json", "X-Client": "codereview-cli/0.3.0", "X-Trace": "bench"}
    return {"payload": payload, "headers": headers, "note": "这一行故意写得很长，用来触发 PY-LONG-FUNC 规则，长度超过一百个字符以便测试"}
