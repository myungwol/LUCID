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
        super().__init__(timeout=None) # 버튼 무제한 유지

    @ui.button(label="🔒 티켓 종료 (관리자)", style=discord.ButtonStyle.red, custom_id="ticket_close_thread_btn", emoji="⛔")
    async def close_ticket(self, interaction: discord.Interaction, button: ui.Button):
        # --- A. 권한 체크 (관리자 확인) ---
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        supabase: Client = create_client(url, key)
        
        # 1. DB에서 설정된 '관리자 역할' ID 가져오기
        response = supabase.table("server_settings").select("ticket_role_id").eq("guild_id", interaction.guild_id).execute()
        
        has_permission = False
        
        # 2. '관리자(Administrator)' 권한이 있거나, DB에 설정된 '티켓 관리 역할'이 있는지 확인
        if interaction.user.guild_permissions.administrator:
            has_permission = True
        elif response.data and response.data[0]['ticket_role_id']:
            role_id = response.data[0]['ticket_role_id']
            # 유저가 가진 역할 중에 티켓 관리 역할이 있는지 확인
            if any(role.id == role_id for role in interaction.user.roles):
                has_permission = True
        
        if not has_permission:
            await interaction.response.send_message("❌ **관리자**만 티켓을 종료할 수 있습니다.", ephemeral=True)
            return

        # --- B. 유저 내보내기 및 스레드 잠금 ---
        await interaction.response.send_message("🔒 티켓을 종료하고 유저를 내보냅니다...", ephemeral=False)
        
        thread = interaction.channel
        # 스레드가 맞는지 확인
        if not isinstance(thread, discord.Thread):
            await interaction.response.send_message("❌ 이곳은 스레드가 아닙니다.", ephemeral=True)
            return

        # 스레드에 있는 멤버들 중 '봇'과 '종료 버튼 누른 관리자'를 제외하고 모두 내보냄 (즉, 문의한 유저)
        members = await thread.fetch_members()
        for member in members:
            # 멤버 객체 가져오기 (fetch_members는 id만 줄 때도 있어서 get_member로 확인)
            target = interaction.guild.get_member(member.id)
            if target and not target.bot and target.id != interaction.user.id:
                try:
                    await thread.remove_user(target)
                except Exception as e:
                    print(f"유저 내보내기 실패: {e}")

        # 스레드 잠금 (아카이브 & 잠금)
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
        # 비공개 스레드 생성 (Private Thread)
        try:
            # 채널이 텍스트 채널인지 확인 (포럼 등에서는 에러 날 수 있음)
            if not isinstance(interaction.channel, discord.TextChannel):
                await interaction.response.send_message("❌ 텍스트 채널에서만 티켓을 열 수 있습니다.", ephemeral=True)
                return

            # 스레드 이름: ticket-유저명
            thread_name = f"ticket-{interaction.user.name}"
            
            # 비공개 스레드 만들기 (type=private_thread)
            # auto_archive_duration=1440 (24시간 동안 채팅 없으면 보관됨)
            thread = await interaction.channel.create_thread(
                name=thread_name,
                type=discord.ChannelType.private_thread,
                auto_archive_duration=1440,
                reason="티켓 생성"
            )

            # 유저 초대 (스레드는 만든 뒤에 유저를 추가해야 함)
            await thread.add_user(interaction.user)

            # 관리자(역할) 초대 로직
            url = os.getenv('SUPABASE_URL')
            key = os.getenv('SUPABASE_KEY')
            supabase: Client = create_client(url, key)
            response = supabase.table("server_settings").select("ticket_role_id").eq("guild_id", interaction.guild_id).execute()
            
            # DB에 설정된 역할이 있으면, 그 역할이 없는 사람은 못 보지만
            # 여기서는 스레드라 '역할 단위' 초대가 안됨. 
            # (스레드는 개별 유저 초대만 가능. 따라서 관리자는 직접 들어와야 함. 
            #  단, 관리자 권한이 있으면 비공개 스레드도 목록에 보임)
            
            await interaction.response.send_message(f"✅ 비공개 티켓이 생성되었습니다! {thread.mention}로 이동해주세요.", ephemeral=True)

            # 스레드 안에 안내 메시지 + 종료 버튼 전송
            embed = discord.Embed(
                title=f"{interaction.user.name}님의 문의 티켓",
                description="관리자와의 1:1 대화방입니다.\n용무가 끝나면 관리자가 티켓을 종료할 것입니다.",
                color=discord.Color.gold()
            )
            # 유저 멘션 (알림용)
            await thread.send(content=f"{interaction.user.mention}", embed=embed, view=TicketCloseView(self.bot))

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

    # 봇 재시작 시 버튼 연결 유지
    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(TicketLaunchView(self.bot))
        self.bot.add_view(TicketCloseView(self.bot))
        print("🎫 스레드 티켓 시스템 로드 완료!")

    # 1. [설정] 티켓 관리자 역할 지정
    @app_commands.command(name="티켓설정", description="티켓을 관리(종료)할 수 있는 역할을 설정합니다.")
    @app_commands.describe(role="관리자 역할")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_ticket_role(self, interaction: discord.Interaction, role: discord.Role):
        data = {
            "guild_id": interaction.guild_id,
            "ticket_role_id": role.id
        }
        self.supabase.table("server_settings").upsert(data).execute()
        await interaction.response.send_message(f"✅ 설정 완료! 이제 **{role.name}** 역할을 가진 사람이 티켓을 종료할 수 있습니다.", ephemeral=True)

    # 2. [패널] 티켓 생성 버튼 만들기
    @app_commands.command(name="티켓패널", description="문의하기 버튼이 담긴 패널을 생성합니다.")
    @app_commands.describe(channel="패널을 보낼 채널")
    @app_commands.checks.has_permissions(administrator=True)
    async def send_ticket_panel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        embed = discord.Embed(
            title="📬 고객센터 / 1:1 문의",
            description="아래 버튼을 누르면 관리자와 대화할 수 있는 **비공개 스레드**가 열립니다.",
            color=discord.Color.blurple()
        )
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        
        await channel.send(embed=embed, view=TicketLaunchView(self.bot))
        await interaction.response.send_message(f"✅ {channel.mention}에 티켓 패널을 생성했습니다!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(TicketCog(bot))
