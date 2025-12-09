import discord
from discord import app_commands
from discord.ext import commands
from discord import ui
from supabase import create_client, Client
import os
import asyncio

# ==========================================
# 1. [버튼] 티켓 종료 (채널 삭제)
# ==========================================
class TicketCloseView(ui.View):
    def __init__(self):
        super().__init__(timeout=None) # 버튼 무제한 유지

    @ui.button(label="🔒 티켓 종료", style=discord.ButtonStyle.red, custom_id="ticket_close_btn", emoji="🗑️")
    async def close_ticket(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("⚠️ 5초 뒤에 티켓(채널)이 삭제됩니다...", ephemeral=False)
        await asyncio.sleep(5)
        await interaction.channel.delete()

# ==========================================
# 2. [버튼] 티켓 생성 (문의하기)
# ==========================================
class TicketLaunchView(ui.View):
    def __init__(self, bot):
        self.bot = bot
        super().__init__(timeout=None) # 버튼 무제한 유지

    @ui.button(label="📩 문의하기", style=discord.ButtonStyle.primary, custom_id="ticket_create_btn", emoji="🎫")
    async def create_ticket(self, interaction: discord.Interaction, button: ui.Button):
        # 1. DB에서 설정된 '관리자 역할' 가져오기
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        supabase: Client = create_client(url, key)
        
        response = supabase.table("server_settings").select("ticket_role_id").eq("guild_id", interaction.guild_id).execute()
        
        # 설정이 안 되어 있으면 기본적으로 서버 관리자만 봄
        support_role_id = None
        if response.data and response.data[0]['ticket_role_id']:
            support_role_id = response.data[0]['ticket_role_id']

        # 2. 채널 권한 설정 (Overwrites)
        guild = interaction.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False), # 일반 유저는 못 봄
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True), # 신청자는 봄
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True) # 봇도 봄
        }

        # 관리자 역할 추가
        if support_role_id:
            role = guild.get_role(support_role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        # 3. 비공개 채널 생성
        try:
            # 채널 이름: ticket-유저명
            channel_name = f"ticket-{interaction.user.name}"
            ticket_channel = await guild.create_text_channel(name=channel_name, overwrites=overwrites, reason="티켓 생성")
            
            await interaction.response.send_message(f"✅ 티켓이 생성되었습니다! {ticket_channel.mention}로 이동해주세요.", ephemeral=True)

            # 4. 티켓 채널 안에 안내 메시지 + 종료 버튼 전송
            embed = discord.Embed(
                title=f"{interaction.user.name}님의 티켓",
                description="문의하실 내용을 적어주세요.\n담당자가 곧 확인합니다.\n\n대화가 끝나면 아래 버튼을 눌러 종료해주세요.",
                color=discord.Color.green()
            )
            await ticket_channel.send(content=f"{interaction.user.mention}", embed=embed, view=TicketCloseView())

        except Exception as e:
            await interaction.response.send_message(f"❌ 티켓 생성 중 오류가 발생했습니다: {e}", ephemeral=True)

# ==========================================
# 3. [메인 로직] TicketCog
# ==========================================
class TicketCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        self.supabase: Client = create_client(url, key)

    # 봇이 켜지면 버튼을 다시 등록해서 작동하게 함 (Persistent View)
    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(TicketLaunchView(self.bot))
        self.bot.add_view(TicketCloseView())
        print("🎫 티켓 시스템 버튼 로드 완료!")

    # 1. [설정] 티켓 관리자 역할 지정
    @app_commands.command(name="티켓설정", description="티켓(비공개 채널)을 볼 수 있는 관리자 역할을 설정합니다.")
    @app_commands.describe(role="티켓을 관리할 역할(Role)")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_ticket_role(self, interaction: discord.Interaction, role: discord.Role):
        data = {
            "guild_id": interaction.guild_id,
            "ticket_role_id": role.id
        }
        self.supabase.table("server_settings").upsert(data).execute()
        await interaction.response.send_message(f"✅ 설정 완료! 이제 **{role.name}** 역할을 가진 사람도 티켓을 볼 수 있습니다.", ephemeral=True)

    # 2. [패널] 티켓 생성 버튼 만들기
    @app_commands.command(name="티켓패널", description="문의하기 버튼이 담긴 패널을 생성합니다.")
    @app_commands.describe(channel="패널을 보낼 채널")
    @app_commands.checks.has_permissions(administrator=True)
    async def send_ticket_panel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        embed = discord.Embed(
            title="📬 고객센터 / 문의하기",
            description="아래 버튼을 누르면 관리자와의 **1:1 비공개 대화방**이 생성됩니다.\n장난으로 생성 시 제재될 수 있습니다.",
            color=discord.Color.blurple()
        )
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        
        await channel.send(embed=embed, view=TicketLaunchView(self.bot))
        await interaction.response.send_message(f"✅ {channel.mention}에 티켓 패널을 생성했습니다!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(TicketCog(bot))
