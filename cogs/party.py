import discord
from discord import app_commands
from discord.ext import commands
from discord import ui
from supabase import create_client, Client
import os

# ==========================================
# 1. [팝업 뷰] 모집 유형 선택 (전체 / 동성 / 이성)
# ==========================================
class RecruitSelectView(ui.View):
    def __init__(self, bot, settings, user_profile):
        super().__init__(timeout=60)
        self.bot = bot
        self.settings = settings
        self.profile = user_profile

    async def send_recruit_msg(self, interaction: discord.Interaction, target_channel_id: int, title_prefix: str):
        guild = interaction.guild
        channel = guild.get_channel(target_channel_id)
        
        if not channel:
            await interaction.response.send_message("❌ 해당 모집 채널을 찾을 수 없습니다. (설정 확인 필요)", ephemeral=True)
            return

        # 1. 멘션할 역할 가져오기
        recruit_role_id = self.settings.get('recruit_role_id')
        mention_text = f"<@&{recruit_role_id}>" if recruit_role_id else "@here"

        # 2. 프로필 데이터 정리
        age = self.profile.get('age', '미설정')
        voice = self.profile.get('voice_pitch', '미설정')
        bio = self.profile.get('bio', '소개가 없습니다.')
        
        # 3. 임베드 생성
        embed = discord.Embed(
            title=f"{title_prefix} {interaction.user.display_name}님의 파티 모집!",
            description=f"**{bio}**",
            color=discord.Color.green()
        )
        embed.add_field(name="🎂 나이", value=age, inline=True)
        embed.add_field(name="🎙️ 목소리", value=voice, inline=True)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="버튼을 눌러 파티에 참여하거나 DM을 보내보세요!")

        # 4. 전송
        try:
            # 멘션 + 임베드 전송
            sent_msg = await channel.send(content=mention_text, embed=embed)
            await interaction.response.send_message(f"✅ {channel.mention}에 모집 글을 올렸습니다!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 전송 실패: {e}", ephemeral=True)

    # A. [전체 구인]
    @ui.button(label="전체", style=discord.ButtonStyle.secondary, emoji="🌏")
    async def recruit_all(self, interaction: discord.Interaction, button: ui.Button):
        target_id = self.settings.get('channel_mixed')
        await self.send_recruit_msg(interaction, target_id, "📢 [전체]")

    # B. [동성 구인]
    @ui.button(label="동성", style=discord.ButtonStyle.primary, emoji="👫")
    async def recruit_same(self, interaction: discord.Interaction, button: ui.Button):
        user_roles = [r.id for r in interaction.user.roles]
        male_role = self.settings.get('male_role_id')
        female_role = self.settings.get('female_role_id')
        
        target_id = None
        
        if male_role in user_roles:
            target_id = self.settings.get('channel_male') # 남자가 동성 구인 -> 남자방
        elif female_role in user_roles:
            target_id = self.settings.get('channel_female') # 여자가 동성 구인 -> 여자방
        else:
            await interaction.response.send_message("❌ 성별 역할을 감지할 수 없습니다.", ephemeral=True)
            return

        if target_id:
            await self.send_recruit_msg(interaction, target_id, "🚹🚺 [동성]")
        else:
            await interaction.response.send_message("❌ 해당 성별의 구인 채널이 설정되지 않았습니다.", ephemeral=True)

    # C. [이성 구인]
    @ui.button(label="이성", style=discord.ButtonStyle.danger, emoji="💕")
    async def recruit_opposite(self, interaction: discord.Interaction, button: ui.Button):
        user_roles = [r.id for r in interaction.user.roles]
        male_role = self.settings.get('male_role_id')
        female_role = self.settings.get('female_role_id')
        
        target_id = None
        
        if male_role in user_roles:
            target_id = self.settings.get('channel_female') # 남자가 이성 구인 -> 여자방
        elif female_role in user_roles:
            target_id = self.settings.get('channel_male')   # 여자가 이성 구인 -> 남자방
        else:
            await interaction.response.send_message("❌ 성별 역할을 감지할 수 없습니다.", ephemeral=True)
            return

        if target_id:
            await self.send_recruit_msg(interaction, target_id, "💘 [이성]")
        else:
            await interaction.response.send_message("❌ 해당 성별의 구인 채널이 설정되지 않았습니다.", ephemeral=True)


# ==========================================
# 2. [메인 버튼] 기존 클래스 수정
# ==========================================
class MainTopView(ui.View):
    def __init__(self, bot):
        self.bot = bot
        super().__init__(timeout=None)

    # 1. 모집 버튼 (수정됨)
    @ui.button(label="모집", style=discord.ButtonStyle.green, custom_id="party_recruit_btn", emoji="📢")
    async def recruit_btn(self, interaction: discord.Interaction, button: ui.Button):
        # DB 연결
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        supabase: Client = create_client(url, key)

        # 1. 서버 설정 가져오기
        res_settings = supabase.table("server_settings").select("*").eq("guild_id", interaction.guild_id).execute()
        if not res_settings.data:
            await interaction.response.send_message("⚠️ 서버 설정(모집 채널 등)이 되어있지 않습니다. 관리자에게 문의하세요.", ephemeral=True)
            return
        settings = res_settings.data[0]

        # 2. 유저 프로필 가져오기
        res_profile = supabase.table("user_profiles").select("*").eq("user_id", interaction.user.id).execute()
        
        # 프로필이 없으면 기본값 사용
        user_profile = res_profile.data[0] if res_profile.data else {}
        
        if not user_profile:
             await interaction.response.send_message("⚠️ **프로필이 없습니다!**\n옆의 `프로필` 버튼을 눌러 먼저 정보를 입력해주세요.", ephemeral=True)
             return

        # 3. 투명 메시지("\u200b")에 버튼을 달아서 전송
        view = RecruitSelectView(self.bot, settings, user_profile)
        await interaction.response.send_message("\u200b", view=view, ephemeral=True)

    # 2. 프로필 버튼 (연결됨)
    @ui.button(label="프로필", style=discord.ButtonStyle.primary, custom_id="party_profile_btn", emoji="👤")
    async def profile_btn(self, interaction: discord.Interaction, button: ui.Button):
        from cogs.profile import ProfileEditView
        await interaction.response.send_message("📝 **프로필 설정**\n원하는 항목을 수정하세요.", view=ProfileEditView(), ephemeral=True)

    # 3. 블랙 버튼
    @ui.button(label="블랙", style=discord.ButtonStyle.secondary, custom_id="party_blacklist_btn", emoji="🚫")
    async def blacklist_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("🚧 **블랙리스트 관리 기능**은 개발 중입니다!", ephemeral=True)


# 하단 뷰 (기존 유지)
class MainBottomView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="모집 삭제", style=discord.ButtonStyle.red, custom_id="party_delete_recruit_btn", emoji="🗑️")
    async def delete_recruit_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("🚧 **모집 삭제 기능**은 개발 중입니다!", ephemeral=True)

    @ui.button(label="신청 삭제", style=discord.ButtonStyle.secondary, custom_id="party_cancel_apply_btn", emoji="✖️")
    async def cancel_apply_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("🚧 **신청 취소 기능**은 개발 중입니다!", ephemeral=True)


# ==========================================
# 3. [Cog] 명령어 및 설정
# ==========================================
class PartyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        self.supabase: Client = create_client(url, key)

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(MainTopView(self.bot))
        self.bot.add_view(MainBottomView())

    # [설정 명령어] 관리자가 한번 실행해줘야 함
    @app_commands.command(name="모집설정", description="모집에 필요한 역할과 채널을 설정합니다.")
    @app_commands.describe(
        recruit_role="모집 시 멘션할 역할",
        male_role="남자 성별 역할",
        female_role="여자 성별 역할",
        mixed_channel="전체 구인 채널",
        male_channel="남성 구인 채널(남자들이 보는 곳)",
        female_channel="여성 구인 채널(여자들이 보는 곳)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_recruit_settings(
        self, 
        interaction: discord.Interaction, 
        recruit_role: discord.Role,
        male_role: discord.Role,
        female_role: discord.Role,
        mixed_channel: discord.TextChannel,
        male_channel: discord.TextChannel,
        female_channel: discord.TextChannel
    ):
        data = {
            "guild_id": interaction.guild_id,
            "recruit_role_id": recruit_role.id,
            "male_role_id": male_role.id,
            "female_role_id": female_role.id,
            "channel_mixed": mixed_channel.id,
            "channel_male": male_channel.id,
            "channel_female": female_channel.id
        }
        
        self.supabase.table("server_settings").upsert(data).execute()
        
        embed = discord.Embed(title="✅ 모집 설정 완료", color=discord.Color.blue())
        embed.add_field(name="역할", value=f"멘션: {recruit_role.mention}\n남: {male_role.mention} / 여: {female_role.mention}", inline=False)
        embed.add_field(name="채널", value=f"전체: {mixed_channel.mention}\n남성구인: {male_channel.mention}\n여성구인: {female_channel.mention}", inline=False)
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="메인패널", description="파티 모집/관리 버튼이 달린 메인 패널을 생성합니다.")
    @app_commands.checks.has_permissions(administrator=True)
    async def send_main_panel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        invisible_content = "\u200b" 
        try:
            await channel.send(content=invisible_content, view=MainTopView(self.bot))
            await channel.send(content=invisible_content, view=MainBottomView())
            await interaction.response.send_message(f"✅ {channel.mention}에 메인 패널을 설치했습니다.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 패널 생성 실패: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(PartyCog(bot))
