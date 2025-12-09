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
        
        # 1. 신청 상태 확인
        res = supabase.table("party_applications").select("status").eq("id", self.app_db_id).execute()
        if not res.data or res.data[0]['status'] == 'cancelled':
            await interaction.followup.send("❌ 이미 취소된 신청입니다.")
            try: await interaction.message.delete()
            except: pass
            return

        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            await interaction.followup.send("❌ 서버 정보를 찾을 수 없습니다.")
            return

        # 2. 카테고리 찾기
        settings_res = supabase.table("server_settings").select("*").eq("guild_id", self.guild_id).execute()
        category = None
        if settings_res.data:
            mixed_ch_id = settings_res.data[0].get('channel_mixed')
            if mixed_ch_id:
                base_channel = guild.get_channel(mixed_ch_id)
                if base_channel:
                    category = base_channel.category

        try:
            # 3. 방 생성
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=False),
                guild.me: discord.PermissionOverwrite(connect=True, view_channel=True, manage_channels=True),
                guild.get_member(self.host.id): discord.PermissionOverwrite(connect=True, view_channel=True),
                guild.get_member(self.applicant.id): discord.PermissionOverwrite(connect=True, view_channel=True)
            }

            channel_name = f"💕｜{self.host.name}・{self.applicant.name}"
            new_channel = await guild.create_voice_channel(
                name=channel_name, 
                category=category, 
                overwrites=overwrites, 
                reason="파티 매칭 성공"
            )

            # 4. DM 업데이트
            embed = interaction.message.embeds[0]
            embed.color = discord.Color.green()
            embed.set_footer(text="✅ 매칭 성공! 방이 생성되었습니다.")
            await interaction.edit_original_response(view=None, embed=embed)
            
            # 5. 알림 전송
            await new_channel.send(f"🎉 **매칭 성공!**\n{self.host.mention}님, {self.applicant.mention}님 환영합니다!")

            # 6. 신청자에게 DM
            try:
                await self.applicant.send(f"🎉 **{self.host.name}**님이 파티를 수락했습니다!\n서버의 **{new_channel.name}** 방으로 이동하세요.")
            except:
                pass

            # 7. DB 업데이트
            supabase.table("party_applications").update({"status": "accepted"}).eq("id", self.app_db_id).execute()

        except Exception as e:
            await interaction.followup.send(f"❌ 방 생성 실패: {e}")


# ==========================================
# 2. [채널 뷰] 신청하기 버튼 (쉐도우 밴 완벽 구현)
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

        # 1. 호스트 정보 가져오기
        host = self.bot.get_user(self.host_id)
        if not host:
            try: host = await self.bot.fetch_user(self.host_id)
            except: 
                await interaction.response.send_message("❌ 모집자를 찾을 수 없습니다.", ephemeral=True)
                return

        # 2. [중요] 중복/재신청 체크 (차단된 상태 포함)
        # blocked 상태도 'pending'처럼 취급하여 "이미 신청했습니다"를 띄움
        hist_res = supabase.table("party_applications").select("*").eq("host_id", self.host_id).eq("applicant_id", interaction.user.id).execute()
        
        if hist_res.data:
            status = hist_res.data[0]['status']
            if status == 'pending':
                await interaction.response.send_message("⏳ 이미 신청을 보냈습니다.", ephemeral=True)
                return
            elif status == 'blocked': # 차단된 상태로 신청한 기록이 있을 때
                await interaction.response.send_message("⏳ 이미 신청을 보냈습니다.", ephemeral=True)
                return
            elif status == 'cancelled':
                await interaction.response.send_message("❌ 취소한 내역이 있어 다시 신청할 수 없습니다.", ephemeral=True)
                return
            elif status == 'accepted':
                await interaction.response.send_message("✅ 이미 매칭된 상대입니다.", ephemeral=True)
                return

        # 3. 블랙리스트 체크 & 쉐도우 밴
        blk_res = supabase.table("personal_blacklists").select("*").eq("user_id", self.host_id).eq("target_id", interaction.user.id).execute()
        
        if blk_res.data:
            # ✅ 차단됨: DB에 'blocked' 상태로 저장하고 성공 메시지 출력 (DM은 안 보냄)
            insert_data = {
                "host_id": self.host_id, 
                "applicant_id": interaction.user.id, 
                "status": "blocked" # 특수 상태
            }
            supabase.table("party_applications").insert(insert_data).execute()
            
            await interaction.response.send_message(f"✅ **{host.name}**님에게 신청을 보냈습니다!", ephemeral=True)
            return 

        # 4. 정상 신청 (차단 안됨)
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
# 3. [모달/뷰] 블랙리스트 (토글)
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
        
        # 토글 로직
        res = supabase.table("personal_blacklists").select("*").eq("user_id", interaction.user.id).eq("target_id", target.id).execute()
        
        if res.data:
            supabase.table("personal_blacklists").delete().eq("user_id", interaction.user.id).eq("target_id", target.id).execute()
            await interaction.response.send_message(f"🔓 **{target.name}**님의 차단을 **해제**했습니다.", ephemeral=True)
        else:
            supabase.table("personal_blacklists").insert({"user_id": interaction.user.id, "target_id": target.id}).execute()
            await interaction.response.send_message(f"🚫 **{target.name}**님을 **차단**했습니다.\n이제 이 유저는 나에게 신청을 보낼 수 없습니다.", ephemeral=True)

class BlacklistView(ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(BlacklistUserSelect())


# ==========================================
# 4. [뷰] 모집글 작성
# ==========================================
class RecruitSelectView(ui.View):
    def __init__(self, bot, settings, user_profile):
        super().__init__(timeout=60)
        self.bot = bot
        self.settings = settings
        self.profile = user_profile

    async def send_recruit_msg(self, interaction: discord.Interaction, target_channel_id: int, tag: str):
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

        recruit_role_id = self.settings.get('recruit_role_id')
        mention_text = f"<@&{recruit_role_id}>" if recruit_role_id else ""

        embed = discord.Embed(color=0xFFB6C1)
        embed.set_author(name=f"{tag} 파티 모집", icon_url=interaction.user.display_avatar.url)
        embed.description = (
            f"**👤 이름** : {interaction.user.display_name}\n\n"
            f"**🎂 나이** : {self.profile.get('age', '미설정')}\n\n"
            f"**🎙️ 목소리** : {self.profile.get('voice_pitch', '미설정')}\n\n"
            f"**📝 한마디**\n```{self.profile.get('bio', '없음')}```"
        )
        embed.set_footer(text="아래 버튼을 눌러 신청하세요!")
        embed.set_thumbnail(url=interaction.user.display_avatar.url)

        try:
            view = RecruitApplyView(self.bot, interaction.user.id)
            msg = await channel.send(content=mention_text, embed=embed, view=view)
            
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

    @ui.button(label="전체", style=discord.ButtonStyle.secondary, emoji="🌏")
    async def recruit_all(self, interaction: discord.Interaction, button: ui.Button):
        await self.send_recruit_msg(interaction, self.settings.get('channel_mixed'), "[전체]")

    @ui.button(label="동성", style=discord.ButtonStyle.primary, emoji="👫")
    async def recruit_same(self, interaction: discord.Interaction, button: ui.Button):
        roles = [r.id for r in interaction.user.roles]
        male, female = self.settings.get('male_role_id'), self.settings.get('female_role_id')
        tid = self.settings.get('channel_male') if male in roles else self.settings.get('channel_female') if female in roles else None
        if tid: await self.send_recruit_msg(interaction, tid, "[동성]")
        else: await interaction.response.send_message("❌ 설정 오류", ephemeral=True)

    @ui.button(label="이성", style=discord.ButtonStyle.danger, emoji="💕")
    async def recruit_opposite(self, interaction: discord.Interaction, button: ui.Button):
        roles = [r.id for r in interaction.user.roles]
        male, female = self.settings.get('male_role_id'), self.settings.get('female_role_id')
        tid = self.settings.get('channel_female') if male in roles else self.settings.get('channel_male') if female in roles else None
        if tid: await self.send_recruit_msg(interaction, tid, "[이성]")
        else: await interaction.response.send_message("❌ 설정 오류", ephemeral=True)


# ==========================================
# 5. [메인 패널] 상단/하단
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
            else:
                supabase.table("party_recruits").delete().eq("user_id", interaction.user.id).execute()
                await interaction.followup.send("⚠️ 채널을 찾을 수 없어 DB 데이터만 정리했습니다.", ephemeral=True)

        except discord.NotFound:
            supabase.table("party_recruits").delete().eq("user_id", interaction.user.id).execute()
            await interaction.followup.send("✅ 이미 삭제된 글입니다.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ 오류: {e}", ephemeral=True)

    # 신청 삭제 (blocked 상태도 함께 취소 처리)
    @ui.button(label="신청 삭제", style=discord.ButtonStyle.secondary, custom_id="party_cancel_apply_btn", emoji="✖️")
    async def cancel_apply_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)

        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        supabase: Client = create_client(url, key)

        # pending 또는 blocked 상태인 신청 조회 (in_ 필터 사용)
        res = supabase.table("party_applications").select("*").eq("applicant_id", interaction.user.id).in_("status", ["pending", "blocked"]).execute()
        
        if not res.data:
            await interaction.followup.send("❌ 취소할 대기 중인 신청이 없습니다.", ephemeral=True)
            return

        count = 0
        for app in res.data:
            # 1. 상태 취소로 변경
            supabase.table("party_applications").update({"status": "cancelled"}).eq("id", app['id']).execute()
            
            # 2. DM 삭제 (blocked 상태는 dm_message_id가 비어있을 수 있으므로 체크)
            host_id = app['host_id']
            dm_msg_id = app.get('dm_message_id')
            
            if dm_msg_id:
                try:
                    host = await self.bot.fetch_user(host_id)
                    dm_channel = host.dm_channel or await host.create_dm()
                    msg = await dm_channel.fetch_message(dm_msg_id)
                    await msg.delete()
                except:
                    pass
            count += 1
        
        await interaction.followup.send(f"✅ 총 **{count}**건의 신청을 철회했습니다.", ephemeral=True)


# ==========================================
# 6. [Cog] 메인 및 루프
# ==========================================
class PartyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cleanup_voice_loop.start()

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
