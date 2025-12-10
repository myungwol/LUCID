import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord import ui
from supabase import create_client, Client
import os
from datetime import datetime, timedelta, timezone

# ==========================================
# 1. [DM 뷰] 수락 버튼
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
        if not res.data:
            await interaction.followup.send("❌ 찾을 수 없는 신청입니다.")
            return

        status = res.data[0]['status']
        if status in ['cancelled', 'closed', 'accepted']:
            await interaction.followup.send(f"❌ 유효하지 않은 신청 상태입니다. ({status})")
            try: await interaction.message.delete()
            except: pass
            return

        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            await interaction.followup.send("❌ 서버 정보를 찾을 수 없습니다.")
            return

        settings_res = supabase.table("server_settings").select("*").eq("guild_id", self.guild_id).execute()
        category = None
        if settings_res.data:
            mixed_ch_id = settings_res.data[0].get('channel_mixed')
            if mixed_ch_id:
                base_channel = guild.get_channel(mixed_ch_id)
                if base_channel:
                    category = base_channel.category

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
                            msg_to_delete = await interaction.channel.fetch_message(dm_msg_id)
                            await msg_to_delete.delete()
                        except: pass

        except Exception as e:
            await interaction.followup.send(f"❌ 방 생성 실패: {e}")


# ==========================================
# 2. [채널 뷰] 신청하기 버튼
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

        profile_res = supabase.table("user_profiles").select("user_id").eq("user_id", interaction.user.id).execute()
        if not profile_res.data:
            await interaction.response.send_message("❌ **프로필이 없습니다!**\n먼저 `/메인패널`의 `프로필` 버튼을 눌러 정보를 등록해주세요.", ephemeral=True)
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
                await interaction.response.send_message("❌ 이미 매칭되었거나 마감된 모집입니다.", ephemeral=True)
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

        except discord.Forbidden:
            await interaction.response.send_message("❌ 모집자의 DM이 닫혀있습니다.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 오류: {e}", ephemeral=True)


# ==========================================
# 3. [모달/뷰] 블랙리스트
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
            await interaction.response.send_message("❌ 등록된 게임이 없습니다. 관리자에게 문의하세요.", ephemeral=True)
            return
        
        selected_game_name = self.values[0]
        # 해당 게임의 역할 ID 찾기 (멘션용)
        selected_role_id = None
        for game in self.games:
            if game['name'] == selected_game_name:
                selected_role_id = game['role_id']
                break
        
        # 게임 모집 채널 ID 가져오기
        target_id = self.parent_view.settings.get('channel_game_recruit')
        if not target_id:
             await interaction.response.send_message("❌ **게임 모집 채널**이 설정되지 않았습니다. 관리자에게 문의하세요.", ephemeral=True)
             return

        # 역할 멘션 + 제목
        role_mention = f"<@&{selected_role_id}>" if selected_role_id else ""
        
        # send_recruit_msg 호출 (역할 멘션을 인자로 넘김)
        await self.parent_view.send_recruit_msg(interaction, target_id, f"[{selected_game_name}]", role_mention=role_mention)

class GameRecruitView(ui.View):
    def __init__(self, games, parent_view):
        super().__init__()
        self.add_item(GameRecruitSelect(games, parent_view))


# ==========================================
# 5. [NEW] 게임 역할 받기 (멀티 드롭다운)
# ==========================================
class GameRoleSelect(ui.Select):
    def __init__(self, games):
        self.games = games
        options = []
        for game in games:
            emoji = game['emoji'] if game['emoji'] else "🎮"
            # value에 role_id를 넣어서 처리
            options.append(discord.SelectOption(label=game['name'], emoji=emoji, value=str(game['role_id'])))

        # min_values=0 (아무것도 선택 안하면 해제), max_values=개수
        super().__init__(
            placeholder="받고 싶은 게임 역할을 모두 선택하세요 (중복 가능)", 
            min_values=0, 
            max_values=len(options), 
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        selected_role_ids = [int(val) for val in self.values]
        
        # 관리되는 모든 게임 역할 ID 목록
        all_game_role_ids = [g['role_id'] for g in self.games]

        to_add = []
        to_remove = []

        for role_id in all_game_role_ids:
            role = interaction.guild.get_role(role_id)
            if not role: continue
            
            # 선택된 목록에 있는데 유저가 없으면 -> 추가
            if role_id in selected_role_ids and role not in interaction.user.roles:
                to_add.append(role)
            # 선택된 목록에 없는데 유저가 있으면 -> 삭제
            elif role_id not in selected_role_ids and role in interaction.user.roles:
                to_remove.append(role)
        
        if to_add:
            await interaction.user.add_roles(*to_add)
        if to_remove:
            await interaction.user.remove_roles(*to_remove)

        await interaction.followup.send(f"✅ 역할 업데이트 완료! (추가: {len(to_add)}개, 삭제: {len(to_remove)}개)", ephemeral=True)

class GameRoleView(ui.View):
    def __init__(self, games):
        super().__init__(timeout=None)
        self.add_item(GameRoleSelect(games))


# ==========================================
# 6. [뷰] 모집글 작성 (수정됨: 공백 처리, Footer 삭제, 멘션 처리)
# ==========================================
class RecruitSelectView(ui.View):
    def __init__(self, bot, settings, user_profile):
        super().__init__(timeout=60)
        self.bot = bot
        self.settings = settings
        self.profile = user_profile

    # role_mention 인자 추가
    async def send_recruit_msg(self, interaction: discord.Interaction, target_channel_id: int, tag: str, role_mention: str = None):
        # 쿨타임
        last_str = self.profile.get('last_recruit_at')
        if last_str:
            last = datetime.fromisoformat(last_str.replace('Z', '+00:00'))
            diff = datetime.now(timezone.utc) - last
            if diff < timedelta(minutes=10):
                rem = timedelta(minutes=10) - diff
                m, s = divmod(rem.seconds, 60)
                await interaction.response.send_message(f"⏳ **쿨타임 중!** `{m}분 {s}초` 남음", ephemeral=True)
                return

        channel = interaction.guild.get_channel(target_channel_id)
        if not channel:
            await interaction.response.send_message("❌ 채널 오류", ephemeral=True)
            return

        # 멘션 텍스트 결정 (게임 모집이면 해당 역할, 아니면 기본 모집 역할)
        if role_mention:
            final_mention = role_mention
        else:
            default_role_id = self.settings.get('recruit_role_id')
            final_mention = f"<@&{default_role_id}>" if default_role_id else ""

        # [수정] 한마디 공백 처리
        bio = self.profile.get('bio')
        if not bio or str(bio).lower() == 'none':
            bio_display = "\u200b" # 빈 공백 문자
        else:
            bio_display = f"```{bio}```"

        embed = discord.Embed(color=0xFFB6C1)
        embed.set_author(name=f"{tag} 파티 모집", icon_url=interaction.user.display_avatar.url)
        embed.description = (
            f"**👤 이름** : {interaction.user.display_name}\n\n"
            f"**🎂 나이** : {self.profile.get('age', '미설정')}\n\n"
            f"**🎙️ 목소리** : {self.profile.get('voice_pitch', '미설정')}\n\n"
            f"**📝 한마디**\n{bio_display}"
        )
        # [수정] Footer 삭제 (기본값인 None이 들어가면 안 보임)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)

        try:
            view = RecruitApplyView(self.bot, interaction.user.id)
            msg = await channel.send(content=final_mention, embed=embed, view=view)
            
            url = os.getenv('SUPABASE_URL')
            key = os.getenv('SUPABASE_KEY')
            supabase: Client = create_client(url, key)
            
            supabase.table("party_recruits").upsert({
                "user_id": interaction.user.id,
                "guild_id": interaction.guild.id,
                "channel_id": channel.id,
                "message_id": msg.id
            }).execute()
            
            supabase.table("user_profiles").update({
                "last_recruit_at": datetime.now(timezone.utc).isoformat()
            }).eq("user_id", interaction.user.id).execute()

            await interaction.response.send_message(f"✅ {channel.mention}에 모집글을 올렸습니다!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 오류: {e}", ephemeral=True)

    @ui.button(label="전체", style=discord.ButtonStyle.secondary, emoji="🌏", row=0)
    async def recruit_all(self, interaction: discord.Interaction, button: ui.Button):
        await self.send_recruit_msg(interaction, self.settings.get('channel_mixed'), "[전체]")

    @ui.button(label="동성", style=discord.ButtonStyle.primary, emoji="👫", row=0)
    async def recruit_same(self, interaction: discord.Interaction, button: ui.Button):
        roles = [r.id for r in interaction.user.roles]
        male, female = self.settings.get('male_role_id'), self.settings.get('female_role_id')
        tid = self.settings.get('channel_male') if male in roles else self.settings.get('channel_female') if female in roles else None
        if tid: await self.send_recruit_msg(interaction, tid, "[동성]")
        else: await interaction.response.send_message("❌ 설정 오류", ephemeral=True)

    @ui.button(label="이성", style=discord.ButtonStyle.danger, emoji="💕", row=0)
    async def recruit_opposite(self, interaction: discord.Interaction, button: ui.Button):
        roles = [r.id for r in interaction.user.roles]
        male, female = self.settings.get('male_role_id'), self.settings.get('female_role_id')
        tid = self.settings.get('channel_female') if male in roles else self.settings.get('channel_male') if female in roles else None
        if tid: await self.send_recruit_msg(interaction, tid, "[이성]")
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
# 7. [메인 패널] 상단/하단
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

    # [NEW] 게임 역할 받기 버튼 (프로필 옆에 위치)
    @ui.button(label="게임선택", style=discord.ButtonStyle.primary, custom_id="party_game_select_btn", emoji="🎮")
    async def game_select_btn(self, interaction: discord.Interaction, button: ui.Button):
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        supabase: Client = create_client(url, key)
        
        # DB에서 게임 목록 가져오기
        res = supabase.table("game_roles").select("*").eq("guild_id", interaction.guild_id).execute()
        if not res.data:
            await interaction.response.send_message("❌ 등록된 게임 역할이 없습니다.", ephemeral=True)
            return
            
        await interaction.response.send_message("🎮 **보유할 게임 역할을 선택하세요 (중복 가능):**", view=GameRoleView(res.data), ephemeral=True)

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
        try:
            channel = self.bot.get_channel(rec['channel_id'])
            if channel:
                msg = await channel.fetch_message(rec['message_id'])
                await msg.delete()
            supabase.table("party_recruits").delete().eq("user_id", interaction.user.id).execute()
            await interaction.followup.send("✅ 모집글을 삭제했습니다.", ephemeral=True)
        except:
            supabase.table("party_recruits").delete().eq("user_id", interaction.user.id).execute()
            await interaction.followup.send("✅ (이미 삭제됨) DB 정리 완료.", ephemeral=True)

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
# 8. [Cog] 메인 및 루프
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

    @app_commands.command(name="메인패널")
    @app_commands.checks.has_permissions(administrator=True)
    async def send_main_panel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await channel.send("\u200b", view=MainTopView(self.bot))
        await channel.send("\u200b", view=MainBottomView(self.bot))
        await interaction.response.send_message("✅ 패널 생성 완료", ephemeral=True)

    # [수정됨] 모집설정 명령어에 game_channel 인자 추가
    @app_commands.command(name="모집설정", description="모집 시스템에 필요한 역할과 채널을 설정합니다.")
    @app_commands.describe(
        recruit_role="모집 알림 역할", male_role="남자 역할", female_role="여자 역할",
        mixed_channel="전체 구인 채널", male_channel="남성 구인 채널", female_channel="여성 구인 채널",
        game_channel="게임 구인 전용 채널 (NEW)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_recruit_settings(self, interaction: discord.Interaction,
                                   recruit_role: discord.Role, male_role: discord.Role, female_role: discord.Role,
                                   mixed_channel: discord.TextChannel, male_channel: discord.TextChannel, female_channel: discord.TextChannel,
                                   game_channel: discord.TextChannel):
        data = {
            "guild_id": interaction.guild_id,
            "recruit_role_id": recruit_role.id,
            "male_role_id": male_role.id,
            "female_role_id": female_role.id,
            "channel_mixed": mixed_channel.id,
            "channel_male": male_channel.id,
            "channel_female": female_channel.id,
            "channel_game_recruit": game_channel.id
        }
        self.supabase.table("server_settings").upsert(data).execute()
        await interaction.response.send_message(f"✅ 모집 설정 저장 완료!\n게임 모집 채널: {game_channel.mention}", ephemeral=True)

    # 게임 역할 관련 명령어
    @app_commands.command(name="게임추가", description="게임 역할 패널에 넣을 게임과 역할을 등록합니다.")
    @app_commands.describe(role="지급할 역할", name="게임 이름 (예: LoL)", emoji="버튼에 넣을 이모지 (선택)")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_game_role(self, interaction: discord.Interaction, role: discord.Role, name: str, emoji: str = "🎮"):
        data = {
            "guild_id": interaction.guild_id,
            "role_id": role.id,
            "name": name,
            "emoji": emoji
        }
        self.supabase.table("game_roles").insert(data).execute()
        await interaction.response.send_message(f"✅ **{name}** 게임 역할({role.mention})이 등록되었습니다!", ephemeral=True)

    @app_commands.command(name="게임삭제", description="등록된 게임 역할을 삭제합니다.")
    @app_commands.describe(name="삭제할 게임 이름")
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_game_role(self, interaction: discord.Interaction, name: str):
        self.supabase.table("game_roles").delete().eq("guild_id", interaction.guild_id).eq("name", name).execute()
        await interaction.response.send_message(f"✅ **{name}** 게임이 삭제되었습니다.", ephemeral=True)

    @tasks.loop(minutes=1)
    async def cleanup_voice_loop(self):
        for guild in self.bot.guilds:
            for channel in guild.voice_channels:
                if channel.name.startswith("💕｜"):
                    if len(channel.members) == 0:
                        if channel.created_at:
                            diff = datetime.now(timezone.utc) - channel.created_at
                            if diff > timedelta(minutes=10):
                                try: await channel.delete(reason="빈 방 정리")
                                except: pass

async def setup(bot):
    await bot.add_cog(PartyCog(bot))
