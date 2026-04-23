"""
hello_agent.py — Minimal AWS Bedrock AgentCore Runtime

Deployed via `agentcore configure` + `agentcore deploy`.
Accepts a JSON payload with an "input" key and returns a greeting.
Used by test C5 to verify the full configure → deploy → invoke lifecycle.
"""

from bedrock_agentcore.runtime import BedrockAgentCoreApp

app = BedrockAgentCoreApp()


@app.entrypoint
def handler(payload):
    name = payload.get("input", "World")
    return f"Hello, {name}! AgentCore is working."


if __name__ == "__main__":
    app.run()
