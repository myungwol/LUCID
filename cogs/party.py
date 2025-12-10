import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord import ui
from supabase import create_client, Client
import os
from datetime import datetime, timedelta, timezone

# ==========================================
# 1. [DM 뷰] 일반 모집 수락 버튼 (기존 유지)
# ==========================================
class RecruitAcceptView(ui.View):
    def __init__(self, bot, guild_id: int, host: discord.User, applicant: discord.User, app_db_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id
        self.host = host
        self.applicant = applicant
        self.app_db_id = app_db_id

    @ui.button(label="수락하기", style=discord.ButtonStyle.green, emoji="✅")
    async def accept_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        supabase: Client = create_client(url, key)
        
        res = supabase.table("party_applications").select("status").eq("id", self.app_db_id).execute()
        if not res.data: return

        status = res.data[0]['status']
        if status in ['cancelled', 'closed', 'accepted']:
            try: await interaction.message.delete()
            except: pass
            return

        guild = self.bot.get_guild(self.guild_id)
        if not guild: return

        settings_res = supabase.table("server_settings").select("*").eq("guild_id", self.guild_id).execute()
        category = None
        if settings_res.data:
            mixed_ch_id = settings_res.data[0].get('channel_mixed')
            if mixed_ch_id:
                base_channel = guild.get_channel(mixed_ch_id)
                if base_channel: category = base_channel.category

        try:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=False),
                guild.me: discord.PermissionOverwrite(connect=True, view_channel=True, manage_channels=True),
                guild.get_member(self.host.id): discord.PermissionOverwrite(connect=True, view_channel=True),
                guild.get_member(self.applicant.id): discord.PermissionOverwrite(connect=True, view_channel=True)
            }

            channel_name = f"💕｜{self.host.name}・{self.applicant.name}"
            new_channel = await guild.create_voice_channel(name=channel_name, category=category, overwrites=overwrites)

            embed = interaction.message.embeds[0]
            embed.color = discord.Color.green()
            embed.set_footer(text="✅ 매칭 성공! 방이 생성되었습니다.")
            await interaction.edit_original_response(view=None, embed=embed)
            await new_channel.send(f"🎉 **매칭 성공!**\n{self.host.mention}님, {self.applicant.mention}님 환영합니다!")
            
            try: await self.applicant.send(f"🎉 **{self.host.name}**님이 파티를 수락했습니다!\n서버의 **{new_channel.name}** 방으로 이동하세요.")
            except: pass

            supabase.table("party_applications").update({"status": "accepted"}).eq("id", self.app_db_id).execute()

            other_apps = supabase.table("party_applications").select("*").eq("host_id", self.host.id).eq("status", "pending").neq("id", self.app_db_id).execute()
            if other_apps.data:
                for app in other_apps.data:
                    supabase.table("party_applications").update({"status": "closed"}).eq("id", app['id']).execute()
                    dm_msg_id = app.get('dm_message_id')
                    if dm_msg_id:
                        try:
                            msg = await interaction.channel.fetch_message(dm_msg_id)
                            await msg.delete()
                        except: pass
        except: pass


# ==========================================
# 2. [채널 뷰] 일반 모집 신청 버튼 (기존 유지)
# ==========================================
class RecruitApplyView(ui.View):
    def __init__(self, bot, host_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.host_id = host_id

    @ui.button(label="신청하기", style=discord.ButtonStyle.primary, emoji="💌", custom_id="recruit_apply_btn_v3")
    async def apply_btn(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id == self.host_id:
            await interaction.response.send_message("❌ 자기 자신에게는 신청할 수 없습니다.", ephemeral=True)
            return

        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        supabase: Client = create_client(url, key)

        profile_res = supabase.table("user_profiles").select("*").eq("user_id", interaction.user.id).execute()
        if not profile_res.data:
            await interaction.response.send_message("❌ **프로필이 없습니다!** `/메인패널`에서 먼저 등록해주세요.", ephemeral=True)
            return

        host = self.bot.get_user(self.host_id)
        if not host:
            try: host = await self.bot.fetch_user(self.host_id)
            except: 
                await interaction.response.send_message("❌ 모집자를 찾을 수 없습니다.", ephemeral=True)
                return

        hist_res = supabase.table("party_applications").select("*").eq("host_id", self.host_id).eq("applicant_id", interaction.user.id).execute()
        if hist_res.data:
            status = hist_res.data[0]['status']
            if status in ['pending', 'blocked']:
                await interaction.response.send_message("⏳ 이미 신청을 보냈습니다.", ephemeral=True)
                return
            elif status == 'cancelled':
                await interaction.response.send_message("❌ 취소한 내역이 있어 다시 신청할 수 없습니다.", ephemeral=True)
                return
            elif status in ['accepted', 'closed']:
                await interaction.response.send_message("❌ 이미 마감된 모집입니다.", ephemeral=True)
                return

        blk_res = supabase.table("personal_blacklists").select("*").eq("user_id", self.host_id).eq("target_id", interaction.user.id).execute()
        if blk_res.data:
            supabase.table("party_applications").insert({"host_id": self.host_id, "applicant_id": interaction.user.id, "status": "blocked"}).execute()
            await interaction.response.send_message(f"✅ **{host.name}**님에게 신청을 보냈습니다!", ephemeral=True)
            return 

        try:
            embed = discord.Embed(
                title="💌 파티 신청 도착!",
                description=f"**{interaction.user.name}**님이 파티에 참가하고 싶어합니다.",
                color=discord.Color.gold()
            )
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            embed.add_field(name="신청자 프로필", value=interaction.user.mention, inline=False)
            embed.set_footer(text="수락 버튼을 누르면 1:1 방이 생성됩니다.")

            insert_data = {"host_id": self.host_id, "applicant_id": interaction.user.id, "status": "pending"}
            res = supabase.table("party_applications").insert(insert_data).execute()
            app_id = res.data[0]['id']

            view = RecruitAcceptView(self.bot, interaction.guild_id, host, interaction.user, app_id)
            dm_msg = await host.send(embed=embed, view=view)

            supabase.table("party_applications").update({"dm_message_id": dm_msg.id}).eq("id", app_id).execute()
            await interaction.response.send_message(f"✅ **{host.name}**님에게 신청을 보냈습니다!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 오류: {e}", ephemeral=True)


# ==========================================
# 3. [NEW] 게임 모집 참가 버튼 (그룹방 멘션)
# ==========================================
class GameJoinView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @ui.button(label="참가하기", style=discord.ButtonStyle.success, emoji="🙌", custom_id="game_join_btn")
    async def join_btn(self, interaction: discord.Interaction, button: ui.Button):
        # 1. DB에서 이 메시지 ID로 생성된 음성방 ID 찾기
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        supabase: Client = create_client(url, key)

        res = supabase.table("party_recruits").select("*").eq("message_id", interaction.message.id).execute()
        if not res.data:
            await interaction.response.send_message("❌ 만료되었거나 정보를 찾을 수 없는 모집글입니다.", ephemeral=True)
            return
        
        recruit_data = res.data[0]
        voice_id = recruit_data.get("voice_id")
        
        if not voice_id:
            await interaction.response.send_message("❌ 연결된 음성 채널이 없습니다.", ephemeral=True)
            return

        # 2. 음성방 찾아서 멘션 보내기
        voice_channel = interaction.guild.get_channel(voice_id)
        if not voice_channel:
            await interaction.response.send_message("❌ 음성 채널이 이미 삭제되었습니다.", ephemeral=True)
            return

        # 호스트 차단 여부 체크 (선택 사항)
        host_id = recruit_data['user_id']
        blk = supabase.table("personal_blacklists").select("*").eq("user_id", host_id).eq("target_id", interaction.user.id).execute()
        if blk.data:
            await interaction.response.send_message("🚫 호스트에게 차단되어 참가할 수 없습니다.", ephemeral=True)
            return

        try:
            await voice_channel.send(f"👋 **{interaction.user.mention}**님이 참가를 원합니다! (대기실 입장)")
            await interaction.response.send_message(f"✅ **{voice_channel.name}** 채널에 알림을 보냈습니다!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 알림 전송 실패: {e}", ephemeral=True)


# ==========================================
# 4. [NEW] 게임 모집 선택용 드롭다운
# ==========================================
class GameRecruitSelect(ui.Select):
    def __init__(self, games, parent_view):
        self.parent_view = parent_view
        self.games = games
        options = []
        for game in games:
            emoji = game['emoji'] if game['emoji'] else "🎮"
            options.append(discord.SelectOption(label=game['name'], emoji=emoji, value=game['name']))
        
        if not options:
            options.append(discord.SelectOption(label="등록된 게임 없음", value="none"))

        super().__init__(placeholder="모집할 게임을 선택하세요", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("❌ 등록된 게임이 없습니다.", ephemeral=True)
            return
        
        selected_game_name = self.values[0]
        selected_role_id = None
        for game in self.games:
            if game['name'] == selected_game_name:
                selected_role_id = game['role_id']
                break
        
        target_id = self.parent_view.settings.get('channel_game_recruit')
        if not target_id:
             await interaction.response.send_message("❌ **게임 모집 채널**이 설정되지 않았습니다.", ephemeral=True)
             return

        # 게임 모집 로직 호출
        role_mention = f"<@&{selected_role_id}>" if selected_role_id else ""
        await self.parent_view.start_game_recruit(interaction, target_id, selected_game_name, role_mention)

class GameRecruitView(ui.View):
    def __init__(self, games, parent_view):
        super().__init__()
        self.add_item(GameRecruitSelect(games, parent_view))


# ==========================================
# 5. [뷰] 모집글 작성 (일반/게임 분기 처리)
# ==========================================
class RecruitSelectView(ui.View):
    def __init__(self, bot, settings, user_profile):
        super().__init__(timeout=60)
        self.bot = bot
        self.settings = settings
        self.profile = user_profile

    # 쿨타임 체크 헬퍼
    async def check_cooldown(self, interaction: discord.Interaction):
        last_str = self.profile.get('last_recruit_at')
        if last_str:
            last = datetime.fromisoformat(last_str.replace('Z', '+00:00'))
            diff = datetime.now(timezone.utc) - last
            if diff < timedelta(minutes=10):
                rem = timedelta(minutes=10) - diff
                m, s = divmod(rem.seconds, 60)
                await interaction.response.send_message(f"⏳ **쿨타임 중!** `{m}분 {s}초` 남음", ephemeral=True)
                return False
        return True

    # 1. 일반 모집 (1:1 DM 방식)
    async def send_normal_recruit(self, interaction: discord.Interaction, target_channel_id: int, tag: str):
        if not await self.check_cooldown(interaction): return

        channel = interaction.guild.get_channel(target_channel_id)
        if not channel:
            await interaction.response.send_message("❌ 채널 오류", ephemeral=True)
            return

        default_role_id = self.settings.get('recruit_role_id')
        mention_text = f"<@&{default_role_id}>" if default_role_id else ""
        
        bio = self.profile.get('bio')
        bio_display = f"```{bio}```" if bio and str(bio).lower() != 'none' else "\u200b"

        embed = discord.Embed(color=0xFFB6C1)
        embed.set_author(name=f"{tag} 파티 모집", icon_url=interaction.user.display_avatar.url)
        embed.description = (
            f"**👤 이름** : {interaction.user.display_name}\n\n"
            f"**🎂 나이** : {self.profile.get('age', '미설정')}\n\n"
            f"**🎙️ 목소리** : {self.profile.get('voice_pitch', '미설정')}\n\n"
            f"**📝 한마디**\n{bio_display}"
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)

        try:
            view = RecruitApplyView(self.bot, interaction.user.id)
            msg = await channel.send(content=mention_text, embed=embed, view=view)
            self.save_recruit(interaction, channel.id, msg.id)
            await interaction.response.send_message(f"✅ {channel.mention}에 모집글을 올렸습니다!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 오류: {e}", ephemeral=True)

    # 2. 게임 모집 (즉시 방 생성 + 참가 버튼)
    async def start_game_recruit(self, interaction: discord.Interaction, target_channel_id: int, game_name: str, role_mention: str):
        if not await self.check_cooldown(interaction): return

        target_channel = interaction.guild.get_channel(target_channel_id)
        if not target_channel:
            await interaction.response.send_message("❌ 게임 모집 채널을 찾을 수 없습니다.", ephemeral=True)
            return

        # A. 게임방 생성 (카테고리: 설정된 category_game_id)
        cat_id = self.settings.get('category_game_id')
        category = interaction.guild.get_channel(cat_id) if cat_id else target_channel.category

        try:
            # 방 이름: 🎮｜[게임명] 닉네임
            voice_channel = await interaction.guild.create_voice_channel(
                name=f"🎮｜[{game_name}] {interaction.user.display_name}",
                category=category,
                user_limit=0, # 무제한 or 설정 가능
                reason="게임 파티 모집"
            )
            # 호스트 이동 권한 등은 기본 카테고리 권한을 따름 (필요시 overwrites 추가)
        except Exception as e:
            await interaction.response.send_message(f"❌ 음성방 생성 실패: {e}", ephemeral=True)
            return

        # B. 모집글 전송
        bio = self.profile.get('bio')
        bio_display = f"```{bio}```" if bio and str(bio).lower() != 'none' else "\u200b"

        embed = discord.Embed(color=0x00FF00) # 초록색
        embed.set_author(name=f"🎮 [{game_name}] 파티 모집", icon_url=interaction.user.display_avatar.url)
        embed.description = (
            f"**👤 호스트** : {interaction.user.display_name}\n\n"
            f"**🎙️ 음성방** : {voice_channel.mention}\n\n"
            f"**📝 한마디**\n{bio_display}"
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)

        try:
            view = GameJoinView(self.bot)
            msg = await target_channel.send(content=role_mention, embed=embed, view=view)
            
            # C. DB 저장 (음성방 ID 포함)
            self.save_recruit(interaction, target_channel.id, msg.id, voice_id=voice_channel.id)
            
            await interaction.response.send_message(f"✅ 모집 시작! 음성방({voice_channel.mention})이 생성되었습니다.", ephemeral=True)
        except Exception as e:
            await voice_channel.delete() # 실패 시 방 삭제
            await interaction.response.send_message(f"❌ 오류: {e}", ephemeral=True)

    # DB 저장 공통 함수
    def save_recruit(self, interaction, channel_id, message_id, voice_id=None):
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        supabase: Client = create_client(url, key)
        
        # 이전 모집글 정보는 덮어씌움 (Upsert)
        data = {
            "user_id": interaction.user.id,
            "guild_id": interaction.guild.id,
            "channel_id": channel_id,
            "message_id": message_id,
            "voice_id": voice_id # 게임 모집일 경우에만 저장됨
        }
        supabase.table("party_recruits").upsert(data).execute()
        
        # 쿨타임 갱신
        supabase.table("user_profiles").update({
            "last_recruit_at": datetime.now(timezone.utc).isoformat()
        }).eq("user_id", interaction.user.id).execute()


    @ui.button(label="전체", style=discord.ButtonStyle.secondary, emoji="🌏", row=0)
    async def recruit_all(self, interaction: discord.Interaction, button: ui.Button):
        await self.send_normal_recruit(interaction, self.settings.get('channel_mixed'), "[전체]")

    @ui.button(label="동성", style=discord.ButtonStyle.primary, emoji="👫", row=0)
    async def recruit_same(self, interaction: discord.Interaction, button: ui.Button):
        roles = [r.id for r in interaction.user.roles]
        male, female = self.settings.get('male_role_id'), self.settings.get('female_role_id')
        tid = self.settings.get('channel_male') if male in roles else self.settings.get('channel_female') if female in roles else None
        if tid: await self.send_normal_recruit(interaction, tid, "[동성]")
        else: await interaction.response.send_message("❌ 설정 오류", ephemeral=True)

    @ui.button(label="이성", style=discord.ButtonStyle.danger, emoji="💕", row=0)
    async def recruit_opposite(self, interaction: discord.Interaction, button: ui.Button):
        roles = [r.id for r in interaction.user.roles]
        male, female = self.settings.get('male_role_id'), self.settings.get('female_role_id')
        tid = self.settings.get('channel_female') if male in roles else self.settings.get('channel_male') if female in roles else None
        if tid: await self.send_normal_recruit(interaction, tid, "[이성]")
        else: await interaction.response.send_message("❌ 설정 오류", ephemeral=True)

    @ui.button(label="게임", style=discord.ButtonStyle.success, emoji="🎮", row=1)
    async def recruit_game(self, interaction: discord.Interaction, button: ui.Button):
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        supabase: Client = create_client(url, key)
        res = supabase.table("game_roles").select("*").eq("guild_id", interaction.guild_id).execute()
        if not res.data:
            await interaction.response.send_message("❌ 등록된 게임이 없습니다.", ephemeral=True)
            return
        await interaction.response.send_message("🎮 **모집할 게임을 선택해주세요:**", view=GameRecruitView(res.data, self), ephemeral=True)


# ==========================================
# 6. [NEW] 게임 역할 받기 (버튼 방식)
# ==========================================
class GameRoleButton(ui.Button):
    def __init__(self, role_id, label, emoji):
        super().__init__(style=discord.ButtonStyle.secondary, label=label, emoji=emoji)
        self.role_id = role_id

    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(self.role_id)
        if not role:
            await interaction.response.send_message("❌ 해당 역할을 서버에서 찾을 수 없습니다.", ephemeral=True)
            return

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"🗑️ **{role.name}** 역할을 제거했습니다.", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"✅ **{role.name}** 역할을 받았습니다.", ephemeral=True)

class GameRoleButtonView(ui.View):
    def __init__(self, games):
        super().__init__(timeout=None)
        for game in games:
            emoji = game['emoji'] if game['emoji'] else "🎮"
            self.add_item(GameRoleButton(game['role_id'], game['name'], emoji))


# ==========================================
# 7. [모달/뷰] 블랙리스트
# ==========================================
class BlacklistUserSelect(ui.UserSelect):
    def __init__(self):
        super().__init__(placeholder="차단/해제할 유저를 선택하세요", min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        target = self.values[0]
        if target.id == interaction.user.id:
            await interaction.response.send_message("❌ 자기 자신은 차단할 수 없습니다.", ephemeral=True)
            return

        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        supabase: Client = create_client(url, key)
        
        res = supabase.table("personal_blacklists").select("*").eq("user_id", interaction.user.id).eq("target_id", target.id).execute()
        if res.data:
            supabase.table("personal_blacklists").delete().eq("user_id", interaction.user.id).eq("target_id", target.id).execute()
            await interaction.response.send_message(f"🔓 **{target.name}**님의 차단을 **해제**했습니다.", ephemeral=True)
        else:
            supabase.table("personal_blacklists").insert({"user_id": interaction.user.id, "target_id": target.id}).execute()
            await interaction.response.send_message(f"🚫 **{target.name}**님을 **차단**했습니다.", ephemeral=True)

class BlacklistView(ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(BlacklistUserSelect())


# ==========================================
# 8. [메인 패널] 상단/하단
# ==========================================
class MainTopView(ui.View):
    def __init__(self, bot):
        self.bot = bot
        super().__init__(timeout=None)

    @ui.button(label="모집", style=discord.ButtonStyle.green, custom_id="party_recruit_btn", emoji="📢")
    async def recruit_btn(self, interaction: discord.Interaction, button: ui.Button):
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        supabase: Client = create_client(url, key)
        
        settings = supabase.table("server_settings").select("*").eq("guild_id", interaction.guild_id).execute()
        profile = supabase.table("user_profiles").select("*").eq("user_id", interaction.user.id).execute()
        
        if not settings.data: return await interaction.response.send_message("⚠️ 설정 필요", ephemeral=True)
        if not profile.data: return await interaction.response.send_message("⚠️ 프로필을 먼저 설정하세요.", ephemeral=True)

        await interaction.response.send_message("\u200b", view=RecruitSelectView(self.bot, settings.data[0], profile.data[0]), ephemeral=True)

    @ui.button(label="프로필", style=discord.ButtonStyle.primary, custom_id="party_profile_btn", emoji="👤")
    async def profile_btn(self, interaction: discord.Interaction, button: ui.Button):
        from cogs.profile import ProfileEditView
        await interaction.response.send_message("📝 **프로필 설정**", view=ProfileEditView(), ephemeral=True)

    @ui.button(label="게임역할", style=discord.ButtonStyle.primary, custom_id="party_game_select_btn", emoji="🎮")
    async def game_select_btn(self, interaction: discord.Interaction, button: ui.Button):
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        supabase: Client = create_client(url, key)
        res = supabase.table("game_roles").select("*").eq("guild_id", interaction.guild_id).execute()
        if not res.data:
            await interaction.response.send_message("❌ 등록된 게임 역할이 없습니다.", ephemeral=True)
            return
        await interaction.response.send_message("\u200b", view=GameRoleButtonView(res.data), ephemeral=True)

    @ui.button(label="블랙/해제", style=discord.ButtonStyle.secondary, custom_id="party_blacklist_btn", emoji="🚫")
    async def blacklist_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("🚫 **차단/해제 관리**", view=BlacklistView(), ephemeral=True)

class MainBottomView(ui.View):
    def __init__(self, bot):
        self.bot = bot
        super().__init__(timeout=None)

    @ui.button(label="모집 삭제", style=discord.ButtonStyle.red, custom_id="party_delete_recruit_btn", emoji="🗑️")
    async def delete_recruit_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        supabase: Client = create_client(url, key)
        res = supabase.table("party_recruits").select("*").eq("user_id", interaction.user.id).execute()
        if not res.data:
            await interaction.followup.send("❌ 삭제할 모집글이 없습니다.", ephemeral=True)
            return
        
        rec = res.data[0]
        # 1. 메시지 삭제
        try:
            channel = self.bot.get_channel(rec['channel_id'])
            if channel:
                msg = await channel.fetch_message(rec['message_id'])
                await msg.delete()
        except: pass
        
        # 2. 게임 모집이었으면 생성된 음성방도 삭제
        if rec.get('voice_id'):
            try:
                vc = interaction.guild.get_channel(rec['voice_id'])
                if vc: await vc.delete()
            except: pass

        supabase.table("party_recruits").delete().eq("user_id", interaction.user.id).execute()
        await interaction.followup.send("✅ 모집글(및 음성방)을 삭제했습니다.", ephemeral=True)

    @ui.button(label="신청 삭제", style=discord.ButtonStyle.secondary, custom_id="party_cancel_apply_btn", emoji="✖️")
    async def cancel_apply_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        supabase: Client = create_client(url, key)
        res = supabase.table("party_applications").select("*").eq("applicant_id", interaction.user.id).in_("status", ["pending", "blocked"]).execute()
        if not res.data:
            await interaction.followup.send("❌ 취소할 신청이 없습니다.", ephemeral=True)
            return
        count = 0
        for app in res.data:
            supabase.table("party_applications").update({"status": "cancelled"}).eq("id", app['id']).execute()
            dm_msg_id = app.get('dm_message_id')
            if dm_msg_id:
                try:
                    host = await self.bot.fetch_user(app['host_id'])
                    dm_channel = host.dm_channel or await host.create_dm()
                    msg = await dm_channel.fetch_message(dm_msg_id)
                    await msg.delete()
                except: pass
            count += 1
        await interaction.followup.send(f"✅ 총 **{count}**건의 신청을 철회했습니다.", ephemeral=True)


# ==========================================
# 9. [Cog] 메인
# ==========================================
class PartyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cleanup_voice_loop.start()
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        self.supabase: Client = create_client(url, key)

    def cog_unload(self):
        self.cleanup_voice_loop.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(MainTopView(self.bot))
        self.bot.add_view(MainBottomView(self.bot))
        self.bot.add_view(GameJoinView(self.bot)) # 지속성 추가

    @app_commands.command(name="메인패널")
    @app_commands.checks.has_permissions(administrator=True)
    async def send_main_panel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await channel.send("\u200b", view=MainTopView(self.bot))
        await channel.send("\u200b", view=MainBottomView(self.bot))
        await interaction.response.send_message("✅ 패널 생성 완료", ephemeral=True)

    @app_commands.command(name="모집설정", description="모집 시스템 설정")
    @app_commands.describe(recruit_role="모집 알림 역할", male_role="남자 역할", female_role="여자 역할", mixed_channel="전체 구인 채널", male_channel="남성 구인 채널", female_channel="여성 구인 채널", game_channel="게임 구인 채널", game_category="게임방 생성 카테고리(NEW)")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_recruit_settings(self, interaction: discord.Interaction, recruit_role: discord.Role, male_role: discord.Role, female_role: discord.Role, mixed_channel: discord.TextChannel, male_channel: discord.TextChannel, female_channel: discord.TextChannel, game_channel: discord.TextChannel, game_category: discord.CategoryChannel):
        data = {
            "guild_id": interaction.guild_id,
            "recruit_role_id": recruit_role.id,
            "male_role_id": male_role.id,
            "female_role_id": female_role.id,
            "channel_mixed": mixed_channel.id,
            "channel_male": male_channel.id,
            "channel_female": female_channel.id,
            "channel_game_recruit": game_channel.id,
            "category_game_id": game_category.id
        }
        self.supabase.table("server_settings").upsert(data).execute()
        await interaction.response.send_message(f"✅ 설정 완료!\n게임모집: {game_channel.mention}\n게임방생성: {game_category.name}", ephemeral=True)

    @app_commands.command(name="게임추가", description="게임 역할 등록")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_game_role(self, interaction: discord.Interaction, role: discord.Role, name: str, emoji: str = "🎮"):
        self.supabase.table("game_roles").insert({"guild_id": interaction.guild_id, "role_id": role.id, "name": name, "emoji": emoji}).execute()
        await interaction.response.send_message(f"✅ **{name}** 등록 완료!", ephemeral=True)

    @app_commands.command(name="게임삭제", description="게임 역할 삭제")
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_game_role(self, interaction: discord.Interaction, name: str):
        self.supabase.table("game_roles").delete().eq("guild_id", interaction.guild_id).eq("name", name).execute()
        await interaction.response.send_message(f"✅ **{name}** 삭제 완료.", ephemeral=True)

    @tasks.loop(minutes=1)
    async def cleanup_voice_loop(self):
        for guild in self.bot.guilds:
            for channel in guild.voice_channels:
                # 일반 1:1 방(💕) 또는 게임방(🎮) 정리
                if channel.name.startswith("💕｜") or channel.name.startswith("🎮｜"):
                    if len(channel.members) == 0:
                        if channel.created_at:
                            diff = datetime.now(timezone.utc) - channel.created_at
                            if diff > timedelta(minutes=10):
                                try: await channel.delete(reason="빈 방 정리")
                                except: pass

async def setup(bot):
    await bot.add_cog(PartyCog(bot))
