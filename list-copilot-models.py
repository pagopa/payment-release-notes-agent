import asyncio, os
import copilot

async def main():
    token = os.environ.get("COPILOT_GITHUB_TOKEN")
    client = copilot.CopilotClient(
        github_token=token or None,
        use_logged_in_user=not bool(token),
        log_level="error",
    )
    await client.start()
    try:
        for m in sorted(await client.list_models(), key=lambda m: m.id):
            state = m.policy.state if m.policy else "-"
            mult = m.billing.multiplier if m.billing else None
            print(f"{m.id:30} {state:13} x{mult}  {m.name}")
    finally:
        await client.stop()

asyncio.run(main())