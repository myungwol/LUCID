import discord
from discord import app_commands
from discord.ext import commands
from discord import ui
from supabase import create_client, Client
import os

# ==========================================
# 1. [팝업창] 방 이름 변경 모달
# ==========================================
class VoiceNameModal(ui.Modal, title="방 이름 변경"):
    name = ui.TextInput(label="새로운 방 이름", placeholder="예: 게임할 사람 구함", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.channel.edit(name=self.name.value)
            await interaction.response.send_message(f"✅ 방 이름을 **{self.name.value}**(으)로 변경했습니다!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ 봇에게 채널 관리 권한이 없습니다.", ephemeral=True)
        except discord.HTTPException:
            await interaction.response.send_message("⚠️ 이름 변경을 너무 자주 시도했습니다. 잠시 후 다시 시도해주세요.", ephemeral=True)

# ==========================================
# 2. [팝업창] 인원수 변경 모달
# ==========================================
class VoiceLimitModal(ui.Modal, title="인원 제한 변경"):
    limit = ui.TextInput(label="제한 인원 수 (0 = 무제한)", placeholder="숫자만 입력 (0~99)", required=True, max_length=2)

    async def on_submit(self, interaction: discord.Interaction):
        if not self.limit.value.isdigit():
            await interaction.response.send_message("❌ 숫자만 입력해주세요.", ephemeral=True)
            return
        
        limit_num = int(self.limit.value)
        if limit_num < 0 or limit_num > 99:
            await interaction.response.send_message("❌ 인원은 0명에서 99명 사이로 설정해주세요.", ephemeral=True)
            return

        await interaction.channel.edit(user_limit=limit_num)
        msg = "✅ 인원 제한을 **무제한**으로 변경했습니다!" if limit_num == 0 else f"✅ 인원 제한을 **{limit_num}명**으로 변경했습니다!"
        await interaction.response.send_message(msg, ephemeral=True)

# ==========================================
# 3. [버튼] 컨트롤 패널 뷰 (수정됨: 주인 ID 기억하기)
# ==========================================
class VoiceControlView(ui.View):
    # 버튼을 만들 때 '누가 주인인지(owner_id)' 정보를 받아서 기억해둡니다.
    def __init__(self, owner_id: int):
        super().__init__(timeout=None) 
        self.owner_id = owner_id

    # 버튼을 누른 사람이 주인인지 확인하는 검문소
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ 방 주인만 설정할 수 있습니다.", ephemeral=True)
            return False
        return True

    @ui.button(label="이름 변경", style=discord.ButtonStyle.primary, emoji="✏️")
    async def change_name(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(VoiceNameModal())

    @ui.button(label="인원 변경", style=discord.ButtonStyle.secondary, emoji="👥")
    async def change_limit(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(VoiceLimitModal())

# ==========================================
# 4. [메인 로직] VoiceCog
# ==========================================
class VoiceCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        self.supabase: Client = create_client(url, key)

    @app_commands.command(name="음성설정", description="들어가면 방이 생기는 '생성용 채널'을 지정합니다.")
    @app_commands.describe(channel="유저들이 접속할 생성용 음성 채널")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_voice_maker(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        data = {
            "guild_id": interaction.guild_id,
            "auto_voice_id": channel.id
        }
        self.supabase.table("server_settings").upsert(data).execute()
        await interaction.response.send_message(f"✅ 설정 완료! 이제 **{channel.name}**에 들어오면 개인 방이 생성됩니다.", ephemeral=True)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        response = self.supabase.table("server_settings").select("*").eq("guild_id", member.guild.id).execute()
        if not response.data: return
        
        settings = response.data[0]
        maker_channel_id = settings.get('auto_voice_id')

        # A. [방 생성]
        if after.channel and after.channel.id == maker_channel_id:
            guild = member.guild
            maker_channel = guild.get_channel(maker_channel_id)
            category = maker_channel.category

            new_channel = await guild.create_voice_channel(
                name=f"🎙️ {member.display_name}님의 방",
                category=category,
                reason="자동 음성 채널 생성"
            )

            try:
                await member.move_to(new_channel)
                
                # [수정됨] 채널 관리(manage_channels) 권한은 주지 않습니다!
                # 단순 접속 권한만 확실하게 부여 (이미 있을 수 있지만 안전장치)
                await new_channel.set_permissions(member, connect=True)

                # [수정됨] 뷰(View)를 만들 때 주인의 ID(member.id)를 알려줍니다.
                view = VoiceControlView(owner_id=member.id)
                await new_channel.send(content=member.mention, view=view)

            except Exception as e:
                print(f"Error moving member: {e}")
                await new_channel.delete()

        # B. [방 삭제]
        if before.channel and len(before.channel.members) == 0:
            if before.channel.id != maker_channel_id:
                maker_channel = member.guild.get_channel(maker_channel_id)
                if maker_channel and before.channel.category_id == maker_channel.category_id:
                     await before.channel.delete(reason="빈 음성 채널 정리")

async def setup(bot):
    await bot.add_cog(VoiceCog(bot))
