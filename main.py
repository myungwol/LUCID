import discord
import os
from dotenv import load_dotenv
from supabase import create_client, Client

# 1. 환경변수 불러오기
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

# 2. Supabase 연결
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 3. 봇 설정
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'로그인 성공! {client.user} 봇이 준비되었습니다.')

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # DB에 저장하기
    if message.content.startswith('!기록 '):
        content = message.content[4:] # 명령어 뒤의 내용만 자름
        # 'memo' 테이블의 'text' 컬럼에 데이터 넣기
        data = supabase.table("memo").insert({"text": content}).execute()
        await message.channel.send(f'✅ 저장 완료: {content}')

    # DB에서 불러오기
    if message.content == '!목록':
        # 'memo' 테이블의 모든 데이터 가져오기
        response = supabase.table("memo").select("*").execute()
        data = response.data
        
        if not data:
            await message.channel.send("저장된 메모가 없습니다.")
        else:
            result_text = "📜 **메모 목록**\n"
            for item in data:
                result_text += f"- {item['text']}\n"
            await message.channel.send(result_text)

client.run(TOKEN)