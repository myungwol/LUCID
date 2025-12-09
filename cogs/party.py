import discord
from discord import app_commands
from discord.ext import commands
from discord import ui
from supabase import create_client, Client
import os

# ==========================================
# 1. [버튼] 메인 시스템 컨트롤 패널
# ==========================================
class MainSystemView(ui.View):
    def __init__(self):
        super().__init__(timeout=None) 

    # --- 1번째 줄 (row=0) ---
    
    # 1. 모집 (초록색)
    @ui.button(label="모집", style=discord.ButtonStyle.green, custom_id="party_recruit_btn", emoji="📢", row=0)
    async def recruit_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("🚧 **모집 기능**은 개발 중입니다!", ephemeral=True)

    # 2. 프로필 (파란색) - 위치 이동됨
    @ui.button(label="프로필", style=discord.ButtonStyle.primary, custom_id="party_profile_btn", emoji="👤", row=0)
    async def profile_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("🚧 **프로필 조회 기능**은 개발 중입니다!", ephemeral=True)

    # 3. 블랙 (회색) - 위치 이동됨
    @ui.button(label="블랙", style=discord.ButtonStyle.secondary, custom_id="party_blacklist_btn", emoji="🚫", row=0)
    async def blacklist_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("🚧 **블랙리스트 관리 기능**은 개발 중입니다!", ephemeral=True)


    # --- 2번째 줄 (row=1) ---

    # 4. 모집 삭제 (빨간색)
    @ui.button(label="모집 삭제", style=discord.ButtonStyle.red, custom_id="party_delete_recruit_btn", emoji="🗑️", row=1)
    async def delete_recruit_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("🚧 **모집 삭제 기능**은 개발 중입니다!", ephemeral=True)

    # 5. 신청 삭제 (회색)
    @ui.button(label="신청 삭제", style=discord.ButtonStyle.secondary, custom_id="party_cancel_apply_btn", emoji="✖️", row=1)
    async def cancel_apply_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("🚧 **신청 취소 기능**은 개발 중입니다!", ephemeral=True)


# ==========================================
# 2. [메인 로직] PartyCog
# ==========================================
class PartyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        self.supabase: Client = create_client(url, key)

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(MainSystemView())
        print("🎮 파티 시스템 버튼 로드 완료!")

    @app_commands.command(name="메인패널", description="파티 모집/관리 버튼이 달린 메인 패널을 생성합니다.")
    @app_commands.describe(channel="패널을 보낼 채널")
    @app_commands.checks.has_permissions(administrator=True)
    async def send_main_panel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        invisible_content = "\u200b" 
        try:
            await channel.send(content=invisible_content, view=MainSystemView())
            await interaction.response.send_message(f"✅ {channel.mention}에 메인 패널을 설치했습니다.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 패널 생성 실패: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(PartyCog(bot))
