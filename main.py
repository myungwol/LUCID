import discord
import os
import asyncio
from discord.ext import commands
from dotenv import load_dotenv
from supabase import create_client, Client

# 1. 환경변수 설정
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

# 2. 봇 설정 (이제 Client 대신 commands.Bot을 씁니다)
# command_prefix는 쓰지 않지만(슬래시 커맨드 사용), 설정은 해둬야 합니다.
intents = discord.Intents.default()
intents.message_content = True
intents.members = True # 유저 수를 세려면 이 권한이 꼭 필요합니다!

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix='!',
            intents=intents,
            help_command=None
        )
        # Supabase를 봇에 심어서 어디서든 쓸 수 있게 함
        self.supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    async def setup_hook(self):
        # cogs 폴더에서 파일을 찾아서 로드함
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                await self.load_extension(f'cogs.{filename[:-3]}')
                print(f'⚙️ 로드 완료: {filename}')
        
        # 명령어 동기화
        await self.tree.sync()
        print('✅ 슬래시 커맨드 동기화 완료!')

    async def on_ready(self):
        print(f'로그인 성공! {self.user} (ID: {self.user.id})')
        print('--------------------------------------------------')

bot = MyBot()
bot.run(TOKEN)
