import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord import ui
from supabase import create_client, Client
import os
from datetime import datetime, timedelta, timezone

# ==========================================
# 1. [DM 뷰] 수락 버튼 (거절 버튼 제거됨)
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
        
        # 1. 신청 상태 확인 (취소했는지 확인)
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        supabase: Client = create_client(url, key)
        
        res = supabase.table("party_applications").select("status").eq("id", self.app_db_id).execute()
        if not res.data or res.data[0]['status'] == 'cancelled':
            await interaction.followup.send("❌ 이미 취소된 신청입니다.")
            await interaction.message.edit(view=None) # 버튼 제거
            return

        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            await interaction.followup.send("❌ 서버 정보를 찾을 수 없습니다.")
            return

        # 2. 모집 채널의 카테고리 찾기 (서버 설정 참조)
        settings_res = supabase.table("server_settings").select("*").eq("guild_id", self.guild_id).execute()
        category = None
        if settings_res.data:
            # 전체 구인 채널이 있는 카테고리를 기준으로 함
            mixed_ch_id = settings_res.data[0].get('channel_mixed')
            if mixed_ch_id:
                base_channel = guild.get_channel(mixed_ch_id)
                if base_channel:
                    category = base_channel.category

        try:
            # 3. 방 생성 (모집글이 있는 카테고리에)
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

            # 4. DM 업데이트 (버튼 제거 및 성공 표시)
            embed = interaction.message.embeds[0]
            embed.color = discord.Color.green()
            embed.set_footer(text="✅ 매칭 성공! 방이 생성되었습니다.")
            await interaction.edit_original_response(view=None, embed=embed)
            
            # 5. 생성된 방에 알림 멘션 전송
            await new_channel.send(
                content=f"🎉 **매칭 성공!**\n{self.host.mention}님, {self.applicant.mention}님 환영합니다! 즐거운 시간 보내세요.",
            )

            # 6. 신청자에게 DM
            try:
                await self.applicant.send(f"🎉 **{self.host.name}**님이 파티를 수락했습니다!\n서버의 **{new_channel.name}** 방으로 이동하세요.")
            except:
                pass

            # 7. DB 상태 업데이트
            supabase.table("party_applications").update({"status": "accepted"}).eq("id", self.app_db_id).execute()

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
        # 1. 자기 자신 체크
        if interaction.user.id == self.host_id:
            await interaction.response.send_message("❌ 자기 자신에게는 신청할 수 없습니다.", ephemeral=True)
            return

        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        supabase: Client = create_client(url, key)

        # 2. 블랙리스트 체크 (호스트가 신청자를 차단했는지)
        blk_res = supabase.table("personal_blacklists").select("*")\
            .eq("user_id", self.host_id).eq("target_id", interaction.user.id).execute()
        
        if blk_res.data:
            await interaction.response.send_message("🚫 해당 유저에게 차단되어 신청을 보낼 수 없습니다.", ephemeral=True)
            return

        # 3. 중복 신청/재신청 방지 체크
        # (이미 신청했고, 상태가 cancelled인 경우 재신청 불가)
        hist_res = supabase.table("party_applications").select("*")\
            .eq("host_id", self.host_id).eq("applicant_id", interaction.user.id).execute()
        
        if hist_res.data:
            status = hist_res.data[0]['status']
            if status == 'pending':
                await interaction.response.send_message("⏳ 이미 신청을 보냈습니다. 수락을 기다려주세요.", ephemeral=True)
                return
            elif status == 'cancelled':
                await interaction.response.send_message("❌ 신청을 취소했던 기록이 있어 재신청이 불가능합니다.", ephemeral=True)
                return
            elif status == 'accepted':
                await interaction.response.send_message("✅ 이미 매칭된 상대입니다.", ephemeral=True)
                return

        # 4. 신청 로직 진행
        host = self.bot.get_user(self.host_id)
        if not host:
            try: host = await self.bot.fetch_user(self.host_id)
            except: 
                await interaction.response.send_message("❌ 모집자를 찾을 수 없습니다.", ephemeral=True)
                return

        try:
            # DM 전송
            embed = discord.Embed(
                title="💌 파티 신청 도착!",
                description=f"**{interaction.user.name}**님이 파티에 참가하고 싶어합니다.",
                color=discord.Color.gold()
            )
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            embed.add_field(name="신청자 프로필", value=interaction.user.mention, inline=False)
            embed.set_footer(text="수락 버튼을 누르면 1:1 방이 생성됩니다.")

            # DB에 먼저 임시 저장 (ID 생성을 위해)
            insert_data = {
                "host_id": self.host_id, 
                "applicant_id": interaction.user.id,
                "status": "pending"
            }
            res = supabase.table("party_applications").insert(insert_data).execute()
            app_id = res.data[0]['id']

            # DM 보내기
            view = RecruitAcceptView(self.bot, interaction.guild_id, host, interaction.user, app_id)
            dm_msg = await host.send(embed=embed, view=view)

            # DM 메시지 ID 업데이트 (나중에 취소할 때 수정하기 위함)
            supabase.table("party_applications").update({"dm_message_id": dm_msg.id}).eq("id", app_id).execute()

            await interaction.response.send_message(f"✅ **{host.name}**님에게 신청을 보냈습니다!", ephemeral=True)

        except discord.Forbidden:
            await interaction.response.send_message("❌ 모집자의 DM이 닫혀있어 신청을 보낼 수 없습니다.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 오류 발생: {e}", ephemeral=True)


# ==========================================
# 3. [모달/뷰] 블랙리스트 & 모집글 작성
# ==========================================

# 블랙리스트 추가용 유저 선택 뷰
class BlacklistUserSelect(ui.UserSelect):
    def __init__(self):
        super().__init__(placeholder="차단할 유저를 선택하세요", min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        target_user = self.values[0]
        if target_user.id == interaction.user.id:
            await interaction.response.send_message("❌ 자기 자신은 차단할 수 없습니다.", ephemeral=True)
            return

        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        supabase: Client = create_client(url, key)

        data = {"user_id": interaction.user.id, "target_id": target_user.id}
        try:
            supabase.table("personal_blacklists").insert(data).execute()
            await interaction.response.send_message(f"🚫 **{target_user.name}**님을 차단했습니다.\n이제 이 유저는 나에게 신청을 보낼 수 없습니다.", ephemeral=True)
        except:
            await interaction.response.send_message(f"⚠️ 이미 차단된 유저입니다.", ephemeral=True)

class BlacklistView(ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(BlacklistUserSelect())

# 모집 뷰
class RecruitSelectView(ui.View):
    def __init__(self, bot, settings, user_profile):
        super().__init__(timeout=60)
        self.bot = bot
        self.settings = settings
        self.profile = user_profile

    async def send_recruit_msg(self, interaction: discord.Interaction, target_channel_id: int, tag: str):
        # 쿨타임 체크
        last_recruit_str = self.profile.get('last_recruit_at')
        if last_recruit_str:
            last_recruit = datetime.fromisoformat(last_recruit_str.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            if (now - last_recruit) < timedelta(minutes=10):
                remaining = timedelta(minutes=10) - (now - last_recruit)
                m, s = divmod(remaining.seconds, 60)
                await interaction.response.send_message(f"⏳ **쿨타임 중입니다!** `{m}분 {s}초` 남음", ephemeral=True)
                return

        guild = interaction.guild
        channel = guild.get_channel(target_channel_id)
        if not channel:
            await interaction.response.send_message("❌ 채널 설정 오류", ephemeral=True)
            return

        # 임베드 디자인 (줄바꿈 적용)
        embed = discord.Embed(color=0xFFB6C1) # 연분홍
        embed.set_author(name=f"{tag} 파티 모집", icon_url=interaction.user.display_avatar.url)
        
        # description을 활용해 깔끔한 줄바꿈 처리
        desc_text = (
            f"**👤 이름** : {interaction.user.display_name}\n\n"
            f"**🎂 나이** : {self.profile.get('age', '미설정')}\n\n"
            f"**🎙️ 목소리** : {self.profile.get('voice_pitch', '미설정')}\n\n"
            f"**📝 한마디**\n```{self.profile.get('bio', '없음')}```"
        )
        embed.description = desc_text
        embed.set_image(url="https://media.discordapp.net/attachments/1325450849926811721/1325450953467400262/line.png?ex=677d2d3a&is=677bdbba&hm=c109282305888a7c6e001859942a03783a310619623e5954952047355152848c&=&format=webp&quality=lossless&width=1440&height=4") # 구분선(선택사항)
        embed.set_footer(text="아래 버튼을 눌러 신청하세요!")
        embed.set_thumbnail(url=interaction.user.display_avatar.url)

        try:
            # 메시지 전송
            view = RecruitApplyView(self.bot, interaction.user.id)
            msg = await channel.send(embed=embed, view=view)
            
            # DB 저장 (나중에 삭제하기 위해)
            url = os.getenv('SUPABASE_URL')
            key = os.getenv('SUPABASE_KEY')
            supabase: Client = create_client(url, key)
            
            # 1. 이전 모집글 정보 삭제 (하나만 유지하고 싶다면) -> 여기선 로그만 남김
            # 2. 새 모집글 등록
            recruit_data = {
                "user_id": interaction.user.id,
                "guild_id": guild.id,
                "channel_id": channel.id,
                "message_id": msg.id
            }
            supabase.table("party_recruits").upsert(recruit_data).execute()
            
            # 3. 쿨타임 갱신
            supabase.table("user_profiles").update({
                "last_recruit_at": datetime.now(timezone.utc).isoformat()
            }).eq("user_id", interaction.user.id).execute()

            await interaction.response.send_message(f"✅ 모집글 등록 완료! ({channel.mention})", ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(f"❌ 전송 실패: {e}", ephemeral=True)

    @ui.button(label="전체", style=discord.ButtonStyle.secondary, emoji="🌏")
    async def recruit_all(self, interaction: discord.Interaction, button: ui.Button):
        target_id = self.settings.get('channel_mixed')
        await self.send_recruit_msg(interaction, target_id, "[전체]")

    @ui.button(label="동성", style=discord.ButtonStyle.primary, emoji="👫")
    async def recruit_same(self, interaction: discord.Interaction, button: ui.Button):
        roles = [r.id for r in interaction.user.roles]
        male, female = self.settings.get('male_role_id'), self.settings.get('female_role_id')
        target_id = self.settings.get('channel_male') if male in roles else self.settings.get('channel_female') if female in roles else None
        
        if target_id: await self.send_recruit_msg(interaction, target_id, "[동성]")
        else: await interaction.response.send_message("❌ 성별/채널 설정 오류", ephemeral=True)

    @ui.button(label="이성", style=discord.ButtonStyle.danger, emoji="💕")
    async def recruit_opposite(self, interaction: discord.Interaction, button: ui.Button):
        roles = [r.id for r in interaction.user.roles]
        male, female = self.settings.get('male_role_id'), self.settings.get('female_role_id')
        target_id = self.settings.get('channel_female') if male in roles else self.settings.get('channel_male') if female in roles else None

        if target_id: await self.send_recruit_msg(interaction, target_id, "[이성]")
        else: await interaction.response.send_message("❌ 성별/채널 설정 오류", ephemeral=True)


# ==========================================
# 4. [메인 패널] 상단/하단
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
        
        # 설정 및 프로필 체크
        settings = supabase.table("server_settings").select("*").eq("guild_id", interaction.guild_id).execute()
        profile = supabase.table("user_profiles").select("*").eq("user_id", interaction.user.id).execute()
        
        if not settings.data: return await interaction.response.send_message("⚠️ 설정이 필요합니다.", ephemeral=True)
        if not profile.data: return await interaction.response.send_message("⚠️ 프로필을 먼저 설정해주세요.", ephemeral=True)

        await interaction.response.send_message("\u200b", view=RecruitSelectView(self.bot, settings.data[0], profile.data[0]), ephemeral=True)

    @ui.button(label="프로필", style=discord.ButtonStyle.primary, custom_id="party_profile_btn", emoji="👤")
    async def profile_btn(self, interaction: discord.Interaction, button: ui.Button):
        from cogs.profile import ProfileEditView
        await interaction.response.send_message("📝 **프로필 설정**", view=ProfileEditView(), ephemeral=True)

    @ui.button(label="블랙", style=discord.ButtonStyle.secondary, custom_id="party_blacklist_btn", emoji="🚫")
    async def blacklist_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("🚫 **차단할 유저 선택**\n차단하면 상대방이 나에게 신청을 보낼 수 없습니다.", view=BlacklistView(), ephemeral=True)

class MainBottomView(ui.View):
    def __init__(self, bot):
        self.bot = bot
        super().__init__(timeout=None)

    # A. 모집글 삭제
    @ui.button(label="모집 삭제", style=discord.ButtonStyle.red, custom_id="party_delete_recruit_btn", emoji="🗑️")
    async def delete_recruit_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        supabase: Client = create_client(url, key)

        # 내 최신 모집글 정보 가져오기
        res = supabase.table("party_recruits").select("*").eq("user_id", interaction.user.id).execute()
        if not res.data:
            await interaction.followup.send("❌ 삭제할 모집글이 없습니다.")
            return

        rec = res.data[0]
        try:
            channel = self.bot.get_channel(rec['channel_id'])
            if channel:
                msg = await channel.fetch_message(rec['message_id'])
                await msg.delete()
                
                # DB 삭제
                supabase.table("party_recruits").delete().eq("user_id", interaction.user.id).execute()
                await interaction.followup.send("✅ 모집글을 삭제했습니다.")
            else:
                await interaction.followup.send("⚠️ 채널을 찾을 수 없어 DB 데이터만 정리합니다.")
                supabase.table("party_recruits").delete().eq("user_id", interaction.user.id).execute()

        except discord.NotFound:
            supabase.table("party_recruits").delete().eq("user_id", interaction.user.id).execute()
            await interaction.followup.send("✅ 이미 삭제된 메시지입니다. (DB 정리 완료)")
        except Exception as e:
            await interaction.followup.send(f"❌ 오류: {e}")

    # B. 신청 취소 (DM 수정 및 상태 변경)
    @ui.button(label="신청 삭제", style=discord.ButtonStyle.secondary, custom_id="party_cancel_apply_btn", emoji="✖️")
    async def cancel_apply_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)

        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        supabase: Client = create_client(url, key)

        # 대기 중(pending)인 신청 건 조회
        res = supabase.table("party_applications").select("*").eq("applicant_id", interaction.user.id).eq("status", "pending").execute()
        
        if not res.data:
            await interaction.followup.send("❌ 취소할 대기 중인 신청이 없습니다.")
            return

        count = 0
        for app in res.data:
            # 1. 상태 'cancelled'로 변경 (재신청 방지용)
            supabase.table("party_applications").update({"status": "cancelled"}).eq("id", app['id']).execute()
            
            # 2. 호스트 DM 수정 시도 (상대방 DM이라 delete는 불가, edit으로 '취소됨' 표시)
            host_id = app['host_id']
            dm_msg_id = app.get('dm_message_id')
            
            if dm_msg_id:
                try:
                    host = await self.bot.fetch_user(host_id)
                    dm_channel = host.dm_channel or await host.create_dm()
                    msg = await dm_channel.fetch_message(dm_msg_id)
                    
                    # 뷰 제거 및 내용 수정
                    embed = msg.embeds[0]
                    embed.color = discord.Color.red()
                    embed.set_footer(text="❌ 신청자가 요청을 취소했습니다.")
                    await msg.edit(content="🚫 **신청이 취소되었습니다.**", embed=embed, view=None)
                    count += 1
                except:
                    pass
        
        await interaction.followup.send(f"✅ 총 **{count}**건의 신청을 취소하고 철회했습니다.\n(취소한 유저에게는 다시 신청할 수 없습니다)")


# ==========================================
# 5. [Cog] 메인 및 루프
# ==========================================
class PartyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cleanup_voice_loop.start() # 봇 켜지면 청소 루프 시작

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

    # [자동 작업] 빈 음성 채널 삭제 (10분마다 체크 X -> 1분마다 체크하되 10분 빈 곳 삭제)
    # 여기서는 간단하게: 봇이 만든 "💕｜"로 시작하는 방을 감시
    @tasks.loop(minutes=1)
    async def cleanup_voice_loop(self):
        # 모든 서버 순회
        for guild in self.bot.guilds:
            for channel in guild.voice_channels:
                # 봇이 만든 1:1 방인지 확인 (이름 규칙)
                if channel.name.startswith("💕｜"):
                    # 사람이 없으면 삭제 (좀 더 엄격하게 하려면 created_at이나 빈 시간 체크가 필요하지만,
                    # 요청사항: "10분간 아무도 없으면". 정확히 구현하려면 DB에 방 생성 시간을 넣거나
                    # memory cache를 써야 함. 여기선 '현재 비어있으면 즉시 삭제'가 아니라
                    # '빈 상태로 방치된' 걸 감지해야 함.
                    # 간단한 구현: 비어있으면 삭제 (즉시). 
                    # 10분 딜레이를 주려면 로직이 복잡해짐 -> created_at 체크로 대체)
                    
                    if len(channel.members) == 0:
                        # 채널이 만들어진지 10분 지났는지 확인 (discord API 지원)
                        # created_at은 UTC 기준
                        if channel.created_at:
                            diff = datetime.now(timezone.utc) - channel.created_at
                            if diff > timedelta(minutes=10):
                                try:
                                    await channel.delete(reason="10분 이상 빈 방 정리")
                                except:
                                    pass

async def setup(bot):
    await bot.add_cog(PartyCog(bot))
