import asyncio, time, os
from dotenv import load_dotenv; load_dotenv('.env')
from emergentintegrations.llm.openai import OpenAITextToSpeech
K=os.environ['EMERGENT_LLM_KEY']
async def one(i,model,instr=None):
    t=time.time()
    kw={"instructions":instr} if instr else {}
    await OpenAITextToSpeech(api_key=K).generate_speech(text=f"Era teimosa. Mas também era sábia. Uma coisa não impede a outra {i}.",model=model,voice="coral",**kw)
    print(model,i,round(time.time()-t,2))
async def main():
    await asyncio.gather(*[one(i,"gpt-4o-mini-tts","Fala em português de Portugal, de forma natural.") for i in range(3)], one(9,"tts-1"), one(10,"tts-1-hd"))
asyncio.run(main())
