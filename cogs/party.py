import discord
from discord import app_commands
from discord.ext import commands
from discord import ui
from supabase import create_client, Client
import os

# ==========================================
# 1. [상단 버튼] 모집 / 프로필 / 블랙
# ==========================================
class MainTopView(ui.View):
    def __init__(self):
        super().__init__(timeout=None) 

    # 1. 모집 (초록색)
    @ui.button(label="모집", style=discord.ButtonStyle.green, custom_id="party_recruit_btn", emoji="📢")
    async def recruit_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("🚧 **모집 기능**은 개발 중입니다!", ephemeral=True)

    # 2. 프로필 (파란색) -> 여기를 수정합니다!
    @ui.button(label="프로필", style=discord.ButtonStyle.primary, custom_id="party_profile_btn", emoji="👤")
    async def profile_btn(self, interaction: discord.Interaction, button: ui.Button):
        # 순환 참조 방지를 위해 함수 안에서 import 하거나, 
        # profile.py가 이미 로드되었다면 해당 뷰를 가져옵니다.
        # 가장 쉬운 방법: profile.py의 View를 가져와서 띄우기
        
        from cogs.profile import ProfileEditView
        
        # 현재 설정된 정보를 보여주면서 메뉴를 띄우면 더 좋습니다.
        # (DB 조회를 여기서 할 수도 있지만, 일단 메뉴부터 띄웁니다)
        await interaction.response.send_message("📝 **프로필 설정 메뉴**입니다.\n수정하고 싶은 항목을 선택해주세요.", view=ProfileEditView(), ephemeral=True)

    # 3. 블랙 (회색)
    @ui.button(label="블랙", style=discord.ButtonStyle.secondary, custom_id="party_blacklist_btn", emoji="🚫")
    async def blacklist_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("🚧 **블랙리스트 관리 기능**은 개발 중입니다!", ephemeral=True)


# ==========================================
# 2. [하단 버튼] 모집 삭제 / 신청 삭제
# ==========================================
class MainBottomView(ui.View):
    def __init__(self):
        super().__init__(timeout=None) 

    # 4. 모집 삭제 (빨간색)
    @ui.button(label="모집 삭제", style=discord.ButtonStyle.red, custom_id="party_delete_recruit_btn", emoji="🗑️")
    async def delete_recruit_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("🚧 **모집 삭제 기능**은 개발 중입니다!", ephemeral=True)

    # 5. 신청 삭제 (회색)
    @ui.button(label="신청 삭제", style=discord.ButtonStyle.secondary, custom_id="party_cancel_apply_btn", emoji="✖️")
    async def cancel_apply_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("🚧 **신청 취소 기능**은 개발 중입니다!", ephemeral=True)


# ==========================================
# 3. [메인 로직] PartyCog
# ==========================================
class PartyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        self.supabase: Client = create_client(url, key)

    @commands.Cog.listener()
    async def on_ready(self):
        # 봇 재시작 시 두 뷰(View) 모두 다시 등록해야 작동함
        self.bot.add_view(MainTopView())
        self.bot.add_view(MainBottomView())
        print("🎮 파티 시스템 버튼(상/하단) 로드 완료!")

    @app_commands.command(name="메인패널", description="파티 모집/관리 버튼이 달린 메인 패널을 생성합니다.")
    @app_commands.describe(channel="패널을 보낼 채널")
    @app_commands.checks.has_permissions(administrator=True)
    async def send_main_panel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        invisible_content = "\u200b" 
        
        try:
            # 메시지를 2번 나눠서 보냅니다.
            await channel.send(content=invisible_content, view=MainTopView())
            await channel.send(content=invisible_content, view=MainBottomView())
            
            await interaction.response.send_message(f"✅ {channel.mention}에 메인 패널(2단)을 설치했습니다.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 패널 생성 실패: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(PartyCog(bot))
