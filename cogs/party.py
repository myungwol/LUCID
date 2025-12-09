import discord
from discord import app_commands
from discord.ext import commands
from discord import ui
from supabase import create_client, Client
import os
from datetime import datetime, timedelta, timezone

# ==========================================
# 1. [DM 뷰] 수락 / 거절 버튼 (호스트용)
# ==========================================
class RecruitAcceptView(ui.View):
    def __init__(self, bot, guild_id: int, host: discord.User, applicant: discord.User):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id
        self.host = host
        self.applicant = applicant

    # --- 수락 버튼 ---
    @ui.button(label="수락하기", style=discord.ButtonStyle.green, emoji="✅")
    async def accept_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()

        # 1. 길드 및 멤버 객체 찾기
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            await interaction.followup.send("❌ 서버 정보를 찾을 수 없습니다.")
            return

        try:
            # 2. 1:1 비공개 음성/텍스트 채널 생성 (카테고리는 봇이 있는 곳 or 맨 위)
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=False),
                guild.me: discord.PermissionOverwrite(connect=True, view_channel=True, manage_channels=True),
                # 호스트와 신청자만 입장 가능
                guild.get_member(self.host.id): discord.PermissionOverwrite(connect=True, view_channel=True),
                guild.get_member(self.applicant.id): discord.PermissionOverwrite(connect=True, view_channel=True)
            }

            # 채널 이름 생성
            channel_name = f"💕｜{self.host.name}・{self.applicant.name}"
            
            # 음성 채널 생성 (필요하면 텍스트 채널로 변경 가능)
            new_channel = await guild.create_voice_channel(name=channel_name, overwrites=overwrites, reason="파티 매칭 성공")

            # 3. 호스트에게 성공 메시지 (DM 수정)
            embed = interaction.message.embeds[0]
            embed.color = discord.Color.green()
            embed.set_footer(text="✅ 매칭 성공! 방이 생성되었습니다.")
            await interaction.edit_original_response(content=f"✅ **{new_channel.name}** 방을 생성했습니다!\n바로가기: {new_channel.mention}", embed=embed, view=None)

            # 4. 신청자에게 DM 알림
            try:
                await self.applicant.send(f"🎉 **{self.host.name}**님이 파티 신청을 수락했습니다!\n서버의 **{new_channel.name}** 채널로 이동하세요.")
            except:
                pass

            # 5. [중요] DM 내의 '다른' 수락 버튼들 제거 (Cleanup)
            # 최근 메시지 20개를 훑어서 봇이 보낸 '수락 대기' 메시지가 있다면 버튼을 비활성화
            async for msg in interaction.channel.history(limit=20):
                if msg.author == self.bot.user and msg.id != interaction.message.id:
                    # 임베드가 있고 내용이 파티 신청 관련이라면
                    if msg.embeds and "파티 신청" in msg.embeds[0].title:
                        try:
                            # 뷰를 제거하거나 비활성화된 뷰로 수정
                            disabled_view = ui.View()
                            disabled_view.add_item(ui.Button(label="마감됨", style=discord.ButtonStyle.gray, disabled=True))
                            await msg.edit(view=disabled_view)
                        except:
                            pass

        except Exception as e:
            await interaction.followup.send(f"❌ 방 생성 실패: {e}")

    # --- 거절 버튼 ---
    @ui.button(label="거절하기", style=discord.ButtonStyle.red, emoji="✖️")
    async def deny_btn(self, interaction: discord.Interaction, button: ui.Button):
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()
        embed.set_footer(text="❌ 거절되었습니다.")
        
        await interaction.response.edit_message(content="❌ 신청을 거절했습니다.", embed=embed, view=None)
        
        # (선택) 신청자에게 거절 알림을 보내고 싶으면 주석 해제
        # try:
        #     await self.applicant.send(f"😥 **{self.host.name}**님이 파티 신청을 거절했습니다.")
        # except:
        #     pass


# ==========================================
# 2. [채널 뷰] 신청하기 버튼 (모집글 하단)
# ==========================================
class RecruitApplyView(ui.View):
    def __init__(self, bot, host_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.host_id = host_id

    @ui.button(label="신청하기", style=discord.ButtonStyle.primary, emoji="💌", custom_id="recruit_apply_btn_v2")
    async def apply_btn(self, interaction: discord.Interaction, button: ui.Button):
        # 1. 자기 자신에게 신청 방지
        if interaction.user.id == self.host_id:
            await interaction.response.send_message("❌ 자기 자신에게는 신청할 수 없습니다.", ephemeral=True)
            return

        # 2. 호스트 정보 가져오기
        host = self.bot.get_user(self.host_id)
        if not host:
            # 봇 캐시에 없으면 fetch 시도
            try:
                host = await self.bot.fetch_user(self.host_id)
            except:
                await interaction.response.send_message("❌ 모집자가 존재하지 않거나 찾을 수 없습니다.", ephemeral=True)
                return

        # 3. 호스트에게 DM 전송
        try:
            embed = discord.Embed(
                title="💌 새로운 파티 신청 도착!",
                description=f"**{interaction.user.name}**님이 파티에 참가하고 싶어합니다.",
                color=discord.Color.gold()
            )
            embed.add_field(name="신청자", value=interaction.user.mention, inline=True)
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            embed.set_footer(text="아래 버튼을 눌러 수락하거나 거절하세요.")

            # 수락/거절 뷰 생성 (guild_id를 넘겨줘야 방 생성이 가능)
            view = RecruitAcceptView(self.bot, interaction.guild_id, host, interaction.user)
            
            await host.send(embed=embed, view=view)
            await interaction.response.send_message(f"✅ **{host.name}**님에게 신청 DM을 보냈습니다! 수락을 기다려주세요.", ephemeral=True)
            
        except discord.Forbidden:
            await interaction.response.send_message("❌ 모집자의 DM이 닫혀있어 신청을 보낼 수 없습니다.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 오류 발생: {e}", ephemeral=True)


# ==========================================
# 3. [팝업 뷰] 모집 유형 선택 (전체 / 동성 / 이성)
# ==========================================
class RecruitSelectView(ui.View):
    def __init__(self, bot, settings, user_profile):
        super().__init__(timeout=60)
        self.bot = bot
        self.settings = settings
        self.profile = user_profile

    # 공통 모집 메시지 전송 함수
    async def send_recruit_msg(self, interaction: discord.Interaction, target_channel_id: int, tag: str):
        guild = interaction.guild
        channel = guild.get_channel(target_channel_id)
        
        if not channel:
            await interaction.response.send_message("❌ 모집 채널을 찾을 수 없습니다. (서버 설정 확인 필요)", ephemeral=True)
            return

        # 1. 쿨타임 체크 (DB 확인)
        last_recruit_str = self.profile.get('last_recruit_at')
        if last_recruit_str:
            last_recruit = datetime.fromisoformat(last_recruit_str.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            diff = now - last_recruit
            
            if diff < timedelta(minutes=10):
                remaining = timedelta(minutes=10) - diff
                minutes, seconds = divmod(remaining.seconds, 60)
                await interaction.response.send_message(f"⏳ **쿨타임 중입니다!**\n`{minutes}분 {seconds}초` 뒤에 다시 모집할 수 있습니다.", ephemeral=True)
                return

        # 2. 멘션할 역할
        recruit_role_id = self.settings.get('recruit_role_id')
        mention_text = f"<@&{recruit_role_id}>" if recruit_role_id else ""

        # 3. 프로필 데이터 정리
        name = interaction.user.display_name
        age = self.profile.get('age', '미설정')
        voice = self.profile.get('voice_pitch', '미설정')
        bio = self.profile.get('bio', '소개가 없습니다.')

        # 4. 임베드 디자인 (요청사항 반영: 세로형 깔끔한 디자인)
        embed = discord.Embed(color=discord.Color.from_rgb(255, 182, 193)) # 연분홍색 예시
        embed.set_author(name=f"{tag} 파티 모집", icon_url=interaction.user.display_avatar.url)
        
        # 깔끔한 필드 구성
        embed.add_field(name="👤 이름", value=f"**{name}**", inline=True)
        embed.add_field(name="🎂 나이", value=f"{age}", inline=True)
        embed.add_field(name="🎙️ 목소리", value=f"{voice}", inline=True)
        embed.add_field(name="📝 한마디", value=f"```\n{bio}\n```", inline=False)
        
        embed.set_footer(text="아래 버튼을 눌러 신청하세요!")
        embed.set_thumbnail(url=interaction.user.display_avatar.url)

        # 5. 전송 및 DB 시간 업데이트
        try:
            # 신청 버튼 달아서 전송
            view = RecruitApplyView(self.bot, interaction.user.id)
            await channel.send(content=mention_text, embed=embed, view=view)
            
            # DB에 현재 시간 기록
            url = os.getenv('SUPABASE_URL')
            key = os.getenv('SUPABASE_KEY')
            supabase: Client = create_client(url, key)
            
            supabase.table("user_profiles").update({
                "last_recruit_at": datetime.now(timezone.utc).isoformat()
            }).eq("user_id", interaction.user.id).execute()

            await interaction.response.send_message(f"✅ {channel.mention}에 모집 글을 올렸습니다!", ephemeral=True)
        
        except Exception as e:
            await interaction.response.send_message(f"❌ 전송 실패: {e}", ephemeral=True)

    # 버튼 A. [전체 구인]
    @ui.button(label="전체", style=discord.ButtonStyle.secondary, emoji="🌏")
    async def recruit_all(self, interaction: discord.Interaction, button: ui.Button):
        target_id = self.settings.get('channel_mixed')
        await self.send_recruit_msg(interaction, target_id, "[전체]")

    # 버튼 B. [동성 구인]
    @ui.button(label="동성", style=discord.ButtonStyle.primary, emoji="👫")
    async def recruit_same(self, interaction: discord.Interaction, button: ui.Button):
        user_roles = [r.id for r in interaction.user.roles]
        male_role = self.settings.get('male_role_id')
        female_role = self.settings.get('female_role_id')
        
        target_id = None
        if male_role in user_roles:
            target_id = self.settings.get('channel_male')
        elif female_role in user_roles:
            target_id = self.settings.get('channel_female')
        
        if target_id:
            await self.send_recruit_msg(interaction, target_id, "[동성]")
        else:
            await interaction.response.send_message("❌ 성별 역할을 찾을 수 없거나 채널 설정이 안 되어있습니다.", ephemeral=True)

    # 버튼 C. [이성 구인]
    @ui.button(label="이성", style=discord.ButtonStyle.danger, emoji="💕")
    async def recruit_opposite(self, interaction: discord.Interaction, button: ui.Button):
        user_roles = [r.id for r in interaction.user.roles]
        male_role = self.settings.get('male_role_id')
        female_role = self.settings.get('female_role_id')
        
        target_id = None
        if male_role in user_roles:
            target_id = self.settings.get('channel_female') # 남자는 여자방에
        elif female_role in user_roles:
            target_id = self.settings.get('channel_male')   # 여자는 남자방에
        
        if target_id:
            await self.send_recruit_msg(interaction, target_id, "[이성]")
        else:
            await interaction.response.send_message("❌ 성별 역할을 찾을 수 없거나 채널 설정이 안 되어있습니다.", ephemeral=True)


# ==========================================
# 4. [메인 패널] 상단 버튼
# ==========================================
class MainTopView(ui.View):
    def __init__(self, bot):
        self.bot = bot
        super().__init__(timeout=None)

    @ui.button(label="모집", style=discord.ButtonStyle.green, custom_id="party_recruit_btn", emoji="📢")
    async def recruit_btn(self, interaction: discord.Interaction, button: ui.Button):
        # DB 연결
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        supabase: Client = create_client(url, key)

        # 설정 및 프로필 확인
        res_settings = supabase.table("server_settings").select("*").eq("guild_id", interaction.guild_id).execute()
        if not res_settings.data:
            await interaction.response.send_message("⚠️ 서버 설정이 필요합니다. (/모집설정)", ephemeral=True)
            return
        
        res_profile = supabase.table("user_profiles").select("*").eq("user_id", interaction.user.id).execute()
        user_profile = res_profile.data[0] if res_profile.data else None

        if not user_profile:
             await interaction.response.send_message("⚠️ **프로필이 없습니다!**\n옆의 `프로필` 버튼을 눌러 정보를 입력해주세요.", ephemeral=True)
             return

        # 뷰 실행
        view = RecruitSelectView(self.bot, res_settings.data[0], user_profile)
        await interaction.response.send_message("\u200b", view=view, ephemeral=True)

    @ui.button(label="프로필", style=discord.ButtonStyle.primary, custom_id="party_profile_btn", emoji="👤")
    async def profile_btn(self, interaction: discord.Interaction, button: ui.Button):
        from cogs.profile import ProfileEditView
        await interaction.response.send_message("📝 **프로필 설정**", view=ProfileEditView(), ephemeral=True)

    @ui.button(label="블랙", style=discord.ButtonStyle.secondary, custom_id="party_blacklist_btn", emoji="🚫")
    async def blacklist_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("🚧 준비 중입니다.", ephemeral=True)


# ==========================================
# 5. [메인 패널] 하단 버튼 (기존 유지)
# ==========================================
class MainBottomView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="모집 삭제", style=discord.ButtonStyle.red, custom_id="party_delete_recruit_btn", emoji="🗑️")
    async def delete_recruit_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("🚧 준비 중입니다.", ephemeral=True)

    @ui.button(label="신청 삭제", style=discord.ButtonStyle.secondary, custom_id="party_cancel_apply_btn", emoji="✖️")
    async def cancel_apply_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("🚧 준비 중입니다.", ephemeral=True)


# ==========================================
# 6. [Cog] 파티 시스템 메인
# ==========================================
class PartyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        self.supabase: Client = create_client(url, key)

    @commands.Cog.listener()
    async def on_ready(self):
        # 봇 재시작 시 뷰 지속성 유지
        self.bot.add_view(MainTopView(self.bot))
        self.bot.add_view(MainBottomView())
        
        # '신청하기' 버튼은 메시지에 계속 남아있어야 하므로 지속성 등록이 필요하지만,
        # custom_id를 사용했으므로 여기서 빈 뷰에 등록하거나 핸들러가 필요함.
        # 여기서는 간단히 bot.add_view로 등록 (host_id 동적 처리가 필요하여 완벽한 지속성은 아님, 
        # 봇 재부팅 후 기존 신청 버튼 작동을 위해서는 db에 메시지id 저장이 필요하나 생략)
        # 현재 구조상 재부팅 후 '신청하기' 버튼을 누르면 interaction failed가 뜰 수 있음.
        # 이를 해결하려면 db에 message_id와 host_id를 매핑해야 함. (이번 요청 범위 밖이지만 참고)

    @app_commands.command(name="모집설정", description="모집 시스템에 필요한 역할과 채널을 설정합니다.")
    @app_commands.describe(
        recruit_role="모집 알림 역할", male_role="남자 역할", female_role="여자 역할",
        mixed_channel="전체 구인 채널", male_channel="남성 구인 채널", female_channel="여성 구인 채널"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_recruit_settings(self, interaction: discord.Interaction,
                                   recruit_role: discord.Role, male_role: discord.Role, female_role: discord.Role,
                                   mixed_channel: discord.TextChannel, male_channel: discord.TextChannel, female_channel: discord.TextChannel):
        data = {
            "guild_id": interaction.guild_id,
            "recruit_role_id": recruit_role.id,
            "male_role_id": male_role.id,
            "female_role_id": female_role.id,
            "channel_mixed": mixed_channel.id,
            "channel_male": male_channel.id,
            "channel_female": female_channel.id
        }
        self.supabase.table("server_settings").upsert(data).execute()
        await interaction.response.send_message("✅ 모집 설정이 저장되었습니다!", ephemeral=True)

    @app_commands.command(name="메인패널", description="파티 모집 메인 패널 생성")
    @app_commands.checks.has_permissions(administrator=True)
    async def send_main_panel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await channel.send("\u200b", view=MainTopView(self.bot))
        await channel.send("\u200b", view=MainBottomView())
        await interaction.response.send_message(f"✅ {channel.mention}에 패널 생성 완료", ephemeral=True)

async def setup(bot):
    await bot.add_cog(PartyCog(bot))
