import discord
from discord import ui
from discord.ext import commands
from supabase import create_client, Client
import os

# ==========================================
# 1. [모달] 나이 입력창
# ==========================================
class ProfileAgeModal(ui.Modal, title="나이 설정"):
    age_input = ui.TextInput(
        label="나이",
        placeholder="예: 20살, 24, 20대 중반",
        min_length=1,
        max_length=20
    )

    async def on_submit(self, interaction: discord.Interaction):
        # DB 연결
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        supabase: Client = create_client(url, key)

        data = {
            "user_id": interaction.user.id,
            "age": self.age_input.value
        }
        
        # 데이터 저장 (upsert: 있으면 수정, 없으면 생성)
        supabase.table("user_profiles").upsert(data).execute()
        
        await interaction.response.send_message(f"✅ 나이가 **{self.age_input.value}**(으)로 설정되었습니다!", ephemeral=True)

# ==========================================
# 2. [모달] 한마디 입력창
# ==========================================
class ProfileBioModal(ui.Modal, title="한마디 설정"):
    bio_input = ui.TextInput(
        label="자기소개 (한마디)",
        placeholder="자신을 표현할 짧은 문구를 입력하세요.",
        style=discord.TextStyle.paragraph,
        max_length=100
    )

    async def on_submit(self, interaction: discord.Interaction):
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        supabase: Client = create_client(url, key)

        data = {
            "user_id": interaction.user.id,
            "bio": self.bio_input.value
        }
        
        supabase.table("user_profiles").upsert(data).execute()
        
        await interaction.response.send_message(f"✅ 한마디가 설정되었습니다!\n📄 **내용:** {self.bio_input.value}", ephemeral=True)

# ==========================================
# 3. [뷰+드롭다운] 목소리 톤 선택
# ==========================================
class VoiceSelect(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="고음", emoji="🎼", description="높은 톤의 목소리"),
            discord.SelectOption(label="중고음", emoji="🎵", description="약간 높은 톤"),
            discord.SelectOption(label="중음", emoji="🎹", description="일반적인 톤"),
            discord.SelectOption(label="중저음", emoji="🎸", description="약간 낮은 톤"),
            discord.SelectOption(label="저음", emoji="🔉", description="낮은 톤의 목소리"),
        ]
        super().__init__(placeholder="목소리 톤을 선택해주세요", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_voice = self.values[0]
        
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        supabase: Client = create_client(url, key)

        data = {
            "user_id": interaction.user.id,
            "voice_pitch": selected_voice
        }
        
        supabase.table("user_profiles").upsert(data).execute()
        await interaction.response.send_message(f"✅ 목소리 톤이 **{selected_voice}**(으)로 설정되었습니다!", ephemeral=True)

class VoiceSelectView(ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(VoiceSelect())

# ==========================================
# 4. [뷰+드롭다운] 메인 프로필 메뉴 (나이/한마디/목소리 선택)
# ==========================================
class ProfileMenuSelect(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="나이 설정", emoji="🎂", description="나이를 직접 입력합니다.", value="edit_age"),
            discord.SelectOption(label="한마디 설정", emoji="📝", description="프로필에 표시될 한마디를 적습니다.", value="edit_bio"),
            discord.SelectOption(label="목소리 설정", emoji="🎙️", description="목소리 톤을 선택합니다.", value="edit_voice"),
        ]
        super().__init__(placeholder="수정할 항목을 선택하세요", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        choice = self.values[0]

        if choice == "edit_age":
            await interaction.response.send_modal(ProfileAgeModal())
        
        elif choice == "edit_bio":
            await interaction.response.send_modal(ProfileBioModal())
        
        elif choice == "edit_voice":
            # 목소리 선택은 또 다른 드롭다운을 보여줘야 하므로 새 메시지를 보냅니다.
            await interaction.response.send_message("목소리 톤을 선택해주세요.", view=VoiceSelectView(), ephemeral=True)

class ProfileEditView(ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(ProfileMenuSelect())

# ==========================================
# 5. [Cog] 명령어 연결 (테스트용)
# ==========================================
class ProfileCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # 테스트용 명령어 (나중에 버튼에 연결하면 필요 없을 수도 있음)
    @commands.command(name="프로필수정")
    async def edit_profile_cmd(self, ctx):
        await ctx.send("프로필을 수정합니다.", view=ProfileEditView())

async def setup(bot):
    await bot.add_cog(ProfileCog(bot))
