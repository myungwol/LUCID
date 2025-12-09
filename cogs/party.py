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
        super().__init__(timeout=None) # 버튼이 영원히 작동하도록 설정

    # 1. 모집 버튼 (초록색)
    @ui.button(label="모집", style=discord.ButtonStyle.green, custom_id="party_recruit_btn", emoji="📢")
    async def recruit_btn(self, interaction: discord.Interaction, button: ui.Button):
        # 나중에 여기에 모집 폼(Modal)을 띄우는 코드를 넣을 겁니다.
        await interaction.response.send_message("🚧 **모집 기능**은 개발 중입니다!", ephemeral=True)

    # 2. 모집 삭제 버튼 (빨간색)
    @ui.button(label="모집 삭제", style=discord.ButtonStyle.red, custom_id="party_delete_recruit_btn", emoji="🗑️")
    async def delete_recruit_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("🚧 **모집 삭제 기능**은 개발 중입니다!", ephemeral=True)

    # 3. 신청 삭제 버튼 (회색)
    @ui.button(label="신청 삭제", style=discord.ButtonStyle.secondary, custom_id="party_cancel_apply_btn", emoji="✖️")
    async def cancel_apply_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("🚧 **신청 취소 기능**은 개발 중입니다!", ephemeral=True)

    # 4. 블랙 버튼 (회색)
    @ui.button(label="블랙", style=discord.ButtonStyle.secondary, custom_id="party_blacklist_btn", emoji="🚫")
    async def blacklist_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("🚧 **블랙리스트 관리 기능**은 개발 중입니다!", ephemeral=True)

    # 5. 프로필 버튼 (파란색)
    @ui.button(label="프로필", style=discord.ButtonStyle.primary, custom_id="party_profile_btn", emoji="👤")
    async def profile_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("🚧 **프로필 조회 기능**은 개발 중입니다!", ephemeral=True)


# ==========================================
# 2. [메인 로직] PartyCog
# ==========================================
class PartyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # DB 연결 준비 (나중에 씀)
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        self.supabase: Client = create_client(url, key)

    # 봇이 켜질 때 버튼을 등록해야 재부팅 후에도 클릭이 됩니다.
    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(MainSystemView())
        print("🎮 파티 시스템 버튼 로드 완료!")

    # [명령어] 메인 패널 설치
    @app_commands.command(name="메인패널", description="파티 모집/관리 버튼이 달린 메인 패널을 생성합니다.")
    @app_commands.describe(channel="패널을 보낼 채널")
    @app_commands.checks.has_permissions(administrator=True)
    async def send_main_panel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        # 1. 투명한 메시지를 만들기 위해 'Zero Width Space(폭 없는 공백)' 문자를 사용합니다.
        # 이 문자는 눈에 보이지 않지만 글자로 취급되어 메시지가 전송됩니다.
        invisible_content = "\u200b" 

        # 2. 혹은 투명한 이미지를 담은 임베드를 쓸 수도 있지만, 
        # 가장 깔끔하게 버튼만 띄우려면 내용에 공백 문자만 넣는 게 제일 좋습니다.
        
        try:
            await channel.send(content=invisible_content, view=MainSystemView())
            await interaction.response.send_message(f"✅ {channel.mention}에 메인 패널을 설치했습니다.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 패널 생성 실패: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(PartyCog(bot))
