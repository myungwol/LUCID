import discord
from discord import app_commands
from discord.ext import commands
from discord import ui
from supabase import create_client, Client
import os
import asyncio

# ==========================================
# 1. [버튼] 티켓 종료 (관리자 전용)
# ==========================================
class TicketCloseView(ui.View):
    def __init__(self, bot):
        self.bot = bot
        super().__init__(timeout=None)

    @ui.button(label="🔒 티켓 종료", style=discord.ButtonStyle.red, custom_id="ticket_close_thread_btn", emoji="⛔")
    async def close_ticket(self, interaction: discord.Interaction, button: ui.Button):
        # --- 권한 체크 ---
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        supabase: Client = create_client(url, key)
        
        response = supabase.table("server_settings").select("ticket_role_id").eq("guild_id", interaction.guild_id).execute()
        
        has_permission = False
        if interaction.user.guild_permissions.administrator:
            has_permission = True
        elif response.data and response.data[0]['ticket_role_id']:
            role_id = response.data[0]['ticket_role_id']
            if any(role.id == role_id for role in interaction.user.roles):
                has_permission = True
        
        if not has_permission:
            await interaction.response.send_message("❌ **관리자**만 티켓을 종료할 수 있습니다.", ephemeral=True)
            return

        # --- 종료 로직 ---
        await interaction.response.send_message("🔒 티켓을 종료합합니다...", ephemeral=False)
        
        thread = interaction.channel
        if not isinstance(thread, discord.Thread): return

        # 유저 내보내기 (봇과 관리자 제외)
        members = await thread.fetch_members()
        for member in members:
            target = interaction.guild.get_member(member.id)
            if target and not target.bot and target.id != interaction.user.id:
                try:
                    await thread.remove_user(target)
                except:
                    pass

        # 스레드 잠금 및 보관
        await thread.edit(locked=True, archived=True, reason="관리자에 의한 티켓 종료")


# ==========================================
# 2. [버튼] 티켓 생성 (문의하기)
# ==========================================
class TicketLaunchView(ui.View):
    def __init__(self, bot):
        self.bot = bot
        super().__init__(timeout=None)

    @ui.button(label="📩 문의하기", style=discord.ButtonStyle.primary, custom_id="ticket_create_thread_btn", emoji="💬")
    async def create_ticket(self, interaction: discord.Interaction, button: ui.Button):
        # 1. [중복 방지] 이미 열린 티켓이 있는지 확인 ⭐
        # 채널에 있는 모든 활성 스레드를 검사
        thread_name = f"ticket-{interaction.user.name}"
        for thread in interaction.channel.threads:
            # 이름이 같고, 아직 보관(종료)되지 않은 스레드가 있다면 차단
            if thread.name == thread_name and not thread.archived:
                await interaction.response.send_message(f"❌ 이미 열려있는 티켓이 있습니다! ({thread.mention})", ephemeral=True)
                return

        # 2. 티켓 생성 시작
        try:
            if not isinstance(interaction.channel, discord.TextChannel):
                await interaction.response.send_message("❌ 텍스트 채널에서만 이용 가능합니다.", ephemeral=True)
                return

            # 비공개 스레드 생성
            thread = await interaction.channel.create_thread(
                name=thread_name,
                type=discord.ChannelType.private_thread,
                auto_archive_duration=1440,
                reason="티켓 생성"
            )
            await thread.add_user(interaction.user)
            await interaction.response.send_message(f"✅ 비공개 티켓이 생성되었습니다! {thread.mention}", ephemeral=True)

            # 3. [관리자 호출] 멘션 준비 ⭐
            url = os.getenv('SUPABASE_URL')
            key = os.getenv('SUPABASE_KEY')
            supabase: Client = create_client(url, key)
            response = supabase.table("server_settings").select("ticket_role_id").eq("guild_id", interaction.guild_id).execute()
            
            mention_text = f"{interaction.user.mention}" # 기본은 유저만 멘션
            
            # DB에 저장된 관리자 역할이 있다면 추가 멘션
            if response.data and response.data[0]['ticket_role_id']:
                role_id = response.data[0]['ticket_role_id']
                mention_text += f" <@&{role_id}>" # 역할 멘션 추가

            embed = discord.Embed(
                title=f"{interaction.user.name}님의 문의 티켓",
                description="관리자와의 1:1 대화방입니다.\n용무가 끝나면 관리자가 티켓을 종료할 것입니다.",
                color=discord.Color.gold()
            )
            
            # 멘션과 함께 메시지 전송
            await thread.send(content=mention_text, embed=embed, view=TicketCloseView(self.bot))

        except Exception as e:
            await interaction.response.send_message(f"❌ 오류 발생: {e}", ephemeral=True)


# ==========================================
# 3. [메인 로직] TicketCog
# ==========================================
class TicketCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        self.supabase: Client = create_client(url, key)

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(TicketLaunchView(self.bot))
        self.bot.add_view(TicketCloseView(self.bot))

    @app_commands.command(name="티켓설정", description="티켓을 관리(종료)할 수 있는 역할을 설정합니다.")
    @app_commands.describe(role="관리자 역할")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_ticket_role(self, interaction: discord.Interaction, role: discord.Role):
        data = {
            "guild_id": interaction.guild_id,
            "ticket_role_id": role.id
        }
        self.supabase.table("server_settings").upsert(data).execute()
        await interaction.response.send_message(f"✅ 설정 완료! 이제 **{role.name}** 역할이 티켓 알림을 받고 종료할 수 있습니다.", ephemeral=True)

    @app_commands.command(name="티켓패널", description="문의하기 버튼이 담긴 패널을 생성합니다.")
    @app_commands.checks.has_permissions(administrator=True)
    async def send_ticket_panel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        embed = discord.Embed(
            title="📬 문의",
            description="아래 버튼을 누르면 관리자와 대화할 수 있는 **티켓**이 열립니다.",
            color=discord.Color.blurple()
        )
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        await channel.send(embed=embed, view=TicketLaunchView(self.bot))
        await interaction.response.send_message(f"✅ {channel.mention}에 티켓 패널을 생성했습니다!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(TicketCog(bot))
