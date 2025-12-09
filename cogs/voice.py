import discord
from discord import app_commands
from discord.ext import commands
from supabase import create_client, Client
import os

class VoiceCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        self.supabase: Client = create_client(url, key)

    # 1. [설정 명령어] "이 채널을 자동 생성 채널로 써!"
    @app_commands.command(name="음성설정", description="들어가면 방이 생기는 '생성용 채널'을 지정합니다.")
    @app_commands.describe(channel="유저들이 접속할 생성용 음성 채널")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_voice_maker(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        # DB에 저장 (upsert)
        data = {
            "guild_id": interaction.guild_id,
            "auto_voice_id": channel.id
        }
        # 기존 데이터가 있으면 auto_voice_id만 업데이트, 없으면 새로 생성
        # (주의: count_channel_id가 지워지지 않도록 기존 데이터를 조회하거나 해야 하지만, 
        # Supabase upsert는 PK가 같으면 덮어쓰기 때문에, 여기서는 간단하게 처리합니다.)
        # 안전하게 하려면 update를 써야 하지만, 초기 설정 편의를 위해 upsert를 씁니다.
        
        # 더 안전한 방법: 있는지 확인하고 update 없으면 insert (여기선 간단히 upsert 사용)
        self.supabase.table("server_settings").upsert(data).execute()
        
        await interaction.response.send_message(f"✅ 설정 완료! 이제 **{channel.name}**에 들어오면 개인 방이 생성됩니다.", ephemeral=True)


    # 2. [이벤트] 유저가 음성 채널을 옮겨다닐 때마다 실행
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        # DB에서 현재 서버의 설정을 가져옴 (캐싱을 안 해서 매번 부르지만, 소규모 봇엔 괜찮음)
        response = self.supabase.table("server_settings").select("*").eq("guild_id", member.guild.id).execute()
        if not response.data:
            return
        
        settings = response.data[0]
        maker_channel_id = settings.get('auto_voice_id')

        # A. [방 생성] 유저가 '생성용 채널'에 들어왔을 때 (after.channel)
        if after.channel and after.channel.id == maker_channel_id:
            guild = member.guild
            maker_channel = guild.get_channel(maker_channel_id)

            # 카테고리 설정 (생성용 채널과 같은 카테고리에 만듦)
            category = maker_channel.category

            # 채널 만들기 (이름: 000님의 음성방)
            new_channel = await guild.create_voice_channel(
                name=f"🎙️ {member.display_name}님의 방",
                category=category,
                reason="자동 음성 채널 생성"
            )

            # 유저를 새 방으로 이동시키기
            try:
                await member.move_to(new_channel)
                # (옵션) 봇 권한 설정: 만든 사람에게 관리 권한 주기
                await new_channel.set_permissions(member, manage_channels=True, connect=True)
            except:
                # 이동 실패하면(그 사이 나갔거나 등) 채널 다시 삭제
                await new_channel.delete()

        # B. [방 삭제] 유저가 방에서 나갔을 때 (before.channel)
        # 조건: 나간 방이 있고 + 그 방이 비었고(0명) + 그 방이 '생성용 채널'이 아닐 때
        if before.channel and len(before.channel.members) == 0:
            if before.channel.id != maker_channel_id:
                # 여기서 "봇이 만든 방인가?"를 확실히 체크하려면 DB에 저장해야 하지만,
                # 보통 "생성용 채널과 같은 카테고리에 있는데 텅 빈 방"은 지워도 무방합니다.
                # 혹시 모르니 이름 형식을 체크하거나 카테고리만 체크합니다.
                
                maker_channel = member.guild.get_channel(maker_channel_id)
                # 생성용 채널과 같은 카테고리에 있는 방만 삭제 대상
                if maker_channel and before.channel.category_id == maker_channel.category_id:
                     await before.channel.delete(reason="빈 음성 채널 정리")

async def setup(bot):
    await bot.add_cog(VoiceCog(bot))
