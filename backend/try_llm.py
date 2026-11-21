import asyncio

from app import llm_service


async def main():
    msgs = llm_service.build_messages(
        "You are a helpful assistant. Keep answers concise.", [], "What is the capital of France?"
    )

    print("1) first call (expect LIVE_INFERENCE, key_1)")
    print(await llm_service.get_reply(msgs), "\n")

    print("2) same call again (expect LLM_CACHE, key_id None, same reply)")
    print(await llm_service.get_reply(msgs), "\n")

    print("2b) cache again (should be much faster than 2)")
    print(await llm_service.get_reply(msgs), "\n")

    print("3) key_1=429 (expect LIVE_INFERENCE, key_2, fallback_attempts 1)")
    sim = llm_service.parse_simulation("key_1=429")
    print(await llm_service.get_reply(msgs, sim), "\n")

    print("4) *=429 (expect all providers unavailable)")
    try:
        await llm_service.get_reply(msgs, llm_service.parse_simulation("*=429"))
    except llm_service.AllProvidersUnavailable as e:
        print("Caught:", e)


asyncio.run(main())