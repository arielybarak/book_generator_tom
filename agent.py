import asyncio
import sys
from google.antigravity import Agent, LocalAgentConfig, CapabilitiesConfig

async def main():
    config = LocalAgentConfig(
        api_key="AQ.Ab8RN6KI0jvv1cSPELO0ZT2uAONRoK134gqcuK0j4tbpetO27w",
        system_instructions="You are an expert AI pair programmer with full access to this codebase.",
        capabilities=CapabilitiesConfig()
    )

    print("==================================================")
    print("🤖 Antigravity Agent Ready! (type 'exit' to quit)")
    print("==================================================")

    async with Agent(config) as agent:
        while True:
            try:
                user_input = input("\nYou: ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ("exit", "quit", "q"):
                    print("Goodbye!")
                    break

                print("\nAgent: ", end="", flush=True)
                response = await agent.chat(user_input)
                async for token in response:
                    sys.stdout.write(token)
                    sys.stdout.flush()
                print()
            except (KeyboardInterrupt, EOFError):
                print("\nGoodbye!")
                break

if __name__ == "__main__":
    asyncio.run(main())