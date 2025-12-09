import discord
import os
from dotenv import load_dotenv

# 1. 토큰 불러오기
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# 2. 봇 설정 (권한 설정)
intents = discord.Intents.default()
intents.message_content = True  # 메시지 내용 읽기 권한 켜기

client = discord.Client(intents=intents)

# 3. 봇이 켜졌을 때
@client.event
async def on_ready():
    print(f'로그인 성공! {client.user} 봇이 준비되었습니다.')

# 4. 메시지를 받았을 때
@client.event
async def on_message(message):
    if message.author == client.user: # 자기가 쓴 글은 무시
        return

    if message.content == '!테스트':
        await message.channel.send('성공입니다! 봇이 작동하고 있어요. 🚀')

# 5. 봇 실행
client.run(TOKEN)