import asyncio

from agent_core import ask_agent


async def main():
    print("HYBRID STUDENT AGENT READY - local DB commands + Gemini/Groq fallback\n")
    messages = []

    while True:
        user = input("You: ").strip()
        if user.lower() in {"exit", "quit", "bye"}:
            print("Bye bhai!")
            break

        try:
            reply, messages = await ask_agent(user, messages)
        except Exception as exc:
            reply = f"Agent error: {exc}"

        print("Agent:", reply, "\n")


if __name__ == "__main__":
    asyncio.run(main())
