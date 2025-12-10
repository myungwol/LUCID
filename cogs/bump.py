import discord
from discord import app_commands
from discord.ext import commands, tasks
from supabase import create_client, Client
import os
from datetime import datetime, timedelta, timezone

class BumpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        self.supabase: Client = create_client(url, key)
        
        # 봇 켜지면 타이머 체크 루프 시작
        self.bump_check_loop.start()

    def cog_unload(self):
        self.bump_check_loop.cancel()

    # ==========================================
    # 1. [설정 명령어]
    # ==========================================
    @app_commands.command(name="알림설정", description="범프/업 알림을 받을 역할과 채널을 설정합니다.")
    @app_commands.describe(role="멘션할 역할", channel="알림이 올라올 채널")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_bump_settings(self, interaction: discord.Interaction, role: discord.Role, channel: discord.TextChannel):
        data = {
            "guild_id": interaction.guild_id,
            "bump_role_id": role.id,
            "bump_channel_id": channel.id
        }
        # 설정 저장 (기존 타이머 시간은 유지하거나, 없으면 현재 시간으로 초기화될 수 있음)
        # 여기서는 설정만 저장하고 타이머는 범프가 감지되거나 루프가 돌 때 처리됨
        self.supabase.table("server_settings").upsert(data).execute()
        
        await interaction.response.send_message(f"✅ 설정 완료!\n🔔 **역할**: {role.mention}\n📢 **채널**: {channel.mention}\n(범프나 업을 한 번 실행하면 타이머가 시작됩니다)", ephemeral=True)


    # ==========================================
    # 2. [이벤트 리스너] 범프/업 성공 감지
    # ==========================================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # 봇 자신이 보낸 메시지면 무시
        if message.author.id == self.bot.user.id:
            return
        
        # 봇이 있는 서버인지 확인
        if not message.guild:
            return

        # ---------------------------------------
        # A. 디스보드 (Disboard) 감지
        # ID: 302050872383242240
        # ---------------------------------------
        if message.author.id == 302050872383242240:
            # 임베드 내용 확인 (성공 메시지인지)
            is_success = False
            if message.embeds:
                desc = message.embeds[0].description
                if desc and ("Bumped successfully" in desc or "범프 성공" in desc):
                    is_success = True
            
            if is_success:
                await self.handle_success(message.guild.id, "disboard", 120) # 120분 = 2시간

        # ---------------------------------------
        # B. 코리안봇 (Koreanbot) / 디코올 감지
        # ID: 417015509743501314 (대표적인 한국 봇)
        # ---------------------------------------
        elif message.author.id == 417015509743501314:
            is_success = False
            if message.embeds:
                title = message.embeds[0].title
                if title and ("UP 했습니다" in title or "성공" in title):
                    is_success = True
            
            if is_success:
                await self.handle_success(message.guild.id, "koreanbot", 60) # 60분 = 1시간


    # [공통 로직] 성공 시 멘션 삭제 및 타이머 갱신
    async def handle_success(self, guild_id, bot_type, cooldown_minutes):
        # 1. 설정 가져오기
        res = self.supabase.table("server_settings").select("*").eq("guild_id", guild_id).execute()
        if not res.data: return
        settings = res.data[0]

        channel_id = settings.get('bump_channel_id')
        msg_id_col = f"{bot_type}_msg_id"     # disboard_msg_id 등
        next_at_col = f"{bot_type}_next_at"   # disboard_next_at 등
        
        # 2. 기존 알림 메시지 삭제 (있다면)
        old_msg_id = settings.get(msg_id_col)
        if channel_id and old_msg_id:
            try:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    old_msg = await channel.fetch_message(old_msg_id)
                    await old_msg.delete()
            except:
                pass # 이미 지워졌거나 권한 없으면 패스

        # 3. DB 업데이트 (메시지 ID 초기화, 다음 시간 설정)
        next_time = datetime.now(timezone.utc) + timedelta(minutes=cooldown_minutes)
        
        update_data = {
            msg_id_col: None,  # 알림 삭제했으니 비움
            next_at_col: next_time.isoformat()
        }
        self.supabase.table("server_settings").update(update_data).eq("guild_id", guild_id).execute()
        print(f"⏰ {bot_type} 갱신 완료 (Guild: {guild_id})")


    # ==========================================
    # 3. [자동 루프] 시간 되면 알림 보내기
    # ==========================================
    @tasks.loop(seconds=60) # 1분마다 체크
    async def bump_check_loop(self):
        await self.bot.wait_until_ready()

        # 모든 서버 설정 가져오기
        res = self.supabase.table("server_settings").select("*").execute()
        if not res.data: return

        now = datetime.now(timezone.utc)

        for settings in res.data:
            guild_id = settings['guild_id']
            channel_id = settings.get('bump_channel_id')
            role_id = settings.get('bump_role_id')

            if not channel_id or not role_id: continue
            
            # --- 디스보드 체크 ---
            await self.check_and_send(settings, guild_id, channel_id, role_id, "disboard", now)
            
            # --- 코리안봇 체크 ---
            await self.check_and_send(settings, guild_id, channel_id, role_id, "koreanbot", now)


    async def check_and_send(self, settings, guild_id, channel_id, role_id, bot_type, now):
        next_at_str = settings.get(f"{bot_type}_next_at")
        current_msg_id = settings.get(f"{bot_type}_msg_id")

        # 시간이 설정되어 있고, 아직 알림 메시지를 안 보낸 상태(None)여야 함
        if next_at_str and current_msg_id is None:
            next_at = datetime.fromisoformat(next_at_str.replace('Z', '+00:00'))
            
            # 시간이 됐으면 알림 전송
            if now >= next_at:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    try:
                        # 요청하신 대로 "역할 언급만" 보냄
                        msg = await channel.send(f"<@&{role_id}>")
                        
                        # 보낸 메시지 ID 저장 (나중에 지우기 위해)
                        self.supabase.table("server_settings").update({
                            f"{bot_type}_msg_id": msg.id
                        }).eq("guild_id", guild_id).execute()
                    except Exception as e:
                        print(f"⚠️ 알림 전송 실패 ({bot_type}, {guild_id}): {e}")

async def setup(bot):
    await bot.add_cog(BumpCog(bot))
