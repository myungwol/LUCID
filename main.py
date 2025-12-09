import discord
import os
from dotenv import load_dotenv
from discord import app_commands
from supabase import create_client, Client

# 1. 환경변수 불러오기
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

# 2. Supabase 연결 (나중에 기능을 만들 때 쓰기 위해 연결만 해둠)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 3. 봇 설정 (CommandTree가 슬래시 커맨드를 관리함)
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# 4. 봇이 켜졌을 때 (명령어 동기화)
@client.event
async def on_ready():
    # 슬래시 커맨드를 디스코드 서버에 등록하는 과정
    await tree.sync() 
    print(f'로그인 성공! {client.user} 봇이 준비되었습니다.')
    print('슬래시 커맨드 동기화 완료!')

# ==========================================
# 👇 여기부터 슬래시 커맨드 정의
# ==========================================

# 예시 1: 간단한 인사 커맨드
@tree.command(name="안녕", description="봇이 반갑게 인사를 해줍니다.")
async def hello(interaction: discord.Interaction):
    # interaction.response.send_message가 답장하는 함수입니다.
    await interaction.response.send_message(f"안녕하세요, {interaction.user.name}님! 슬래시 커맨드로 바뀌었어요. 😎")

# 예시 2: 메아리 커맨드 (입력값을 받는 예시)
@tree.command(name="따라해", description="내가 입력한 말을 그대로 따라합니다.")
@app_commands.describe(message="따라할 말을 입력하세요") # 입력창 설명
async def echo(interaction: discord.Interaction, message: str):
    await interaction.response.send_message(f"📢 봇: {message}")

# 봇 실행
client.run(TOKEN)
