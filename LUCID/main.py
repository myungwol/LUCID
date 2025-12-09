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

# 2. Supabase 연결 (지금은 안 쓰지만 연결 유지)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 3. 봇 설정
intents = discord.Intents.default()
intents.message_content = True # 메시지 읽기/삭제 권한 필요
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# 4. 봇이 켜졌을 때
@client.event
async def on_ready():
    await tree.sync()
    print(f'로그인 성공! {client.user} 봇이 준비되었습니다.')
    print('슬래시 커맨드 동기화 완료!')

# ==========================================
# 👇 여기부터 명령어
# ==========================================

# [청소 기능]
# @app_commands.checks.has_permissions : 이 권한이 있는 사람만 쓸 수 있게 막음
@tree.command(name="청소", description="지정한 개수만큼 메시지를 삭제합니다.")
@app_commands.describe(amount="삭제할 메시지의 개수")
@app_commands.checks.has_permissions(manage_messages=True) 
async def clear_chat(interaction: discord.Interaction, amount: int):
    if amount < 1:
        await interaction.response.send_message("1개 이상의 숫자를 입력해주세요.", ephemeral=True)
        return

    # 메시지 삭제 실행 (purge)
    await interaction.response.send_message(f"{amount}개의 메시지를 삭제 중입니다...", ephemeral=True) # 나만 보이게 메시지 보냄
    
    # 실제 삭제 작업 (limit=amount)
    deleted = await interaction.channel.purge(limit=amount)
    
    # 결과 알려주기 (나만 보이게: ephemeral=True)
    await interaction.edit_original_response(content=f"🧹 **{len(deleted)}개**의 메시지를 깨끗하게 청소했습니다!")

# [에러 처리] 권한 없는 사람이 쓰려고 할 때
@clear_chat.error
async def clear_chat_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ **관리 권한(메시지 관리)**이 없어서 실행할 수 없습니다.", ephemeral=True)

# 봇 실행
client.run(TOKEN)
