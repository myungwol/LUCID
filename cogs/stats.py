import discord
from discord import app_commands
from discord.ext import commands, tasks
from supabase import create_client, Client
import os

class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # DB 연결
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        self.supabase: Client = create_client(url, key)
        
        # 봇이 켜지면 '자동 갱신 작업'을 시작함
        self.update_stats_loop.start()

    # 1. 봇이 꺼지면 루프도 멈춤
    def cog_unload(self):
        self.update_stats_loop.cancel()

    # 2. [설정 명령어] 유저가 "이 채널을 써!" 라고 지정하는 명령어
    @app_commands.command(name="스탯설정", description="멤버 수를 표시할 채널을 지정합니다 (음성 채널 추천).")
    @app_commands.describe(channel="이름을 변경할 채널 선택")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_stats_channel(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        # 1. DB에 저장 (upsert: 없으면 만들고, 있으면 수정)
        data = {
            "guild_id": interaction.guild_id,
            "count_channel_id": channel.id
        }
        self.supabase.table("server_settings").upsert(data).execute()

        # 2. 즉시 한 번 변경 시도
        try:
            new_name = f"멤버 수: {interaction.guild.member_count}명"
            await channel.edit(name=new_name)
            await interaction.response.send_message(f"✅ 설정 완료! 이제 **{channel.name}** 채널에 멤버 수가 표시됩니다.\n(자동 갱신은 디스코드 정책상 10분마다 진행됩니다.)")
        except Exception as e:
            await interaction.response.send_message(f"✅ 설정은 저장됐지만, 이름 변경에 실패했습니다. (봇 권한을 확인해주세요)\n에러: {e}")

    # 3. [자동 반복] 10분(minutes=10)마다 실행되는 루프
    @tasks.loop(minutes=6)
    async def update_stats_loop(self):
        # 봇이 완전히 켜질 때까지 기다림
        await self.bot.wait_until_ready()

        # DB에서 설정된 모든 서버 정보를 가져옴
        response = self.supabase.table("server_settings").select("*").execute()
        settings = response.data

        for setting in settings:
            try:
                guild_id = setting['guild_id']
                channel_id = setting['count_channel_id']

                # 봇이 들어가 있는 서버인지 확인
                guild = self.bot.get_guild(guild_id)
                if not guild: continue

                # 채널 찾기
                channel = guild.get_channel(channel_id)
                if not channel: continue

                # 현재 이름과 바꿀 이름이 다를 때만 변경 (API 호출 절약)
                current_count = guild.member_count
                new_name = f"멤버 수: {current_count}명"

                if channel.name != new_name:
                    await channel.edit(name=new_name)
                    print(f"🔄 {guild.name}: 멤버 수 갱신 완료 ({current_count}명)")
            
            except Exception as e:
                print(f"⚠️ 업데이트 실패 (서버ID: {guild_id}): {e}")

async def setup(bot):
    await bot.add_cog(Stats(bot))
