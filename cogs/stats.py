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
        
        # 봇이 켜지면 루프 시작
        self.update_stats_loop.start()

    def cog_unload(self):
        self.update_stats_loop.cancel()

    # ====================================================
    # 1. [설정 명령어] 멤버 수 채널
    # ====================================================
    @app_commands.command(name="스탯설정_멤버", description="전체 멤버 수를 표시할 채널을 지정합니다.")
    @app_commands.describe(channel="이름을 변경할 음성 채널")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_member_stats(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        data = {
            "guild_id": interaction.guild_id,
            "count_channel_id": channel.id
        }
        self.supabase.table("server_settings").upsert(data).execute()

        try:
            new_name = f"멤버 수: {interaction.guild.member_count}명"
            await channel.edit(name=new_name)
            await interaction.response.send_message(f"✅ 설정 완료! **{new_name}** (10분 주기 갱신)")
        except Exception as e:
            await interaction.response.send_message(f"✅ 설정 저장됨. (이름 변경 실패: {e})")

    # ====================================================
    # 2. [설정 명령어] 파티룸 수 채널 (NEW)
    # ====================================================
    @app_commands.command(name="스탯설정_파티룸", description="현재 활성화된 파티룸(매칭방) 개수를 표시할 채널을 지정합니다.")
    @app_commands.describe(channel="이름을 변경할 음성 채널")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_party_stats(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        # 파티룸 개수 계산 (💕｜로 시작하는 채널)
        count = 0
        for vc in interaction.guild.voice_channels:
            if vc.name.startswith("💕｜"):
                count += 1

        data = {
            "guild_id": interaction.guild_id,
            "party_count_channel_id": channel.id
        }
        self.supabase.table("server_settings").upsert(data).execute()

        try:
            new_name = f"💕 활성 파티: {count}개"
            await channel.edit(name=new_name)
            await interaction.response.send_message(f"✅ 설정 완료! **{new_name}** (10분 주기 갱신)")
        except Exception as e:
            await interaction.response.send_message(f"✅ 설정 저장됨. (이름 변경 실패: {e})")

    # ====================================================
    # 3. [자동 루프] 6분마다 상태 갱신
    # ====================================================
    @tasks.loop(minutes=6)
    async def update_stats_loop(self):
        await self.bot.wait_until_ready()

        # DB에서 모든 서버 설정 가져오기
        response = self.supabase.table("server_settings").select("*").execute()
        settings = response.data

        for setting in settings:
            try:
                guild_id = setting['guild_id']
                guild = self.bot.get_guild(guild_id)
                if not guild: continue

                # A. 멤버 수 갱신
                member_ch_id = setting.get('count_channel_id')
                if member_ch_id:
                    ch = guild.get_channel(member_ch_id)
                    if ch:
                        new_name = f"멤버 수: {guild.member_count}명"
                        if ch.name != new_name:
                            await ch.edit(name=new_name)

                # B. 파티룸 수 갱신 (NEW)
                party_ch_id = setting.get('party_count_channel_id')
                if party_ch_id:
                    ch = guild.get_channel(party_ch_id)
                    if ch:
                        # 활성 방 개수 세기
                        party_count = 0
                        for vc in guild.voice_channels:
                            if vc.name.startswith("💕｜"):
                                party_count += 1
                        
                        new_name = f"💕 활성 파티: {party_count}개"
                        if ch.name != new_name:
                            await ch.edit(name=new_name)
            
            except Exception as e:
                print(f"⚠️ 스탯 업데이트 오류 (Guild: {guild_id}): {e}")

async def setup(bot):
    await bot.add_cog(Stats(bot))
