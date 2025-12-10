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
        
        self.bump_check_loop.start()

    def cog_unload(self):
        self.bump_check_loop.cancel()

    # ==========================================
    # 1. [설정 명령어] 역할 & 채널 모두 분리
    # ==========================================
    @app_commands.command(name="알림설정", description="범프/업 알림을 받을 역할과 채널을 각각 설정합니다.")
    @app_commands.describe(
        disboard_role="디스보드(범프) 알림 역할", 
        disboard_channel="디스보드(범프) 알림 채널",
        koreanbot_role="코리안봇(업) 알림 역할", 
        koreanbot_channel="코리안봇(업) 알림 채널"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_bump_settings(self, interaction: discord.Interaction, 
                                disboard_role: discord.Role, disboard_channel: discord.TextChannel,
                                koreanbot_role: discord.Role, koreanbot_channel: discord.TextChannel):
        data = {
            "guild_id": interaction.guild_id,
            "disboard_role_id": disboard_role.id,
            "disboard_channel_id": disboard_channel.id,   # 분리됨
            "koreanbot_role_id": koreanbot_role.id,
            "koreanbot_channel_id": koreanbot_channel.id  # 분리됨
        }
        self.supabase.table("server_settings").upsert(data).execute()
        
        embed = discord.Embed(title="✅ 알림 설정 완료", color=discord.Color.blue())
        embed.add_field(name="🔵 디스보드 (2시간)", value=f"역할: {disboard_role.mention}\n채널: {disboard_channel.mention}", inline=False)
        embed.add_field(name="🔴 코리안봇 (1시간)", value=f"역할: {koreanbot_role.mention}\n채널: {koreanbot_channel.mention}", inline=False)
        embed.set_footer(text="설정 후 범프나 업을 한 번 실행하면 타이머가 시작됩니다.")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


    # ==========================================
    # 2. [이벤트 리스너] 성공 감지 & 삭제
    # ==========================================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.id == self.bot.user.id: return
        if not message.guild: return

        # A. 디스보드 (Disboard)
        if message.author.id == 302050872383242240:
            is_success = False
            if message.embeds:
                desc = message.embeds[0].description
                if desc and ("서버 갱신 완료!" in desc or "범프 성공" in desc):
                    is_success = True
            
            if is_success:
                try: await message.delete()
                except: pass
                await self.handle_success(message.guild.id, "disboard", 120)

        # B. 코리안봇 (Koreanbot)
        elif message.author.id == 664647740877176832:
            is_success = False
            if message.embeds:
                title = message.embeds[0].title
                if title and ("서버가 상단에 표시되었습니다." in title or "성공" in title):
                    is_success = True
            
            if is_success:
                try: await message.delete()
                except: pass
                await self.handle_success(message.guild.id, "koreanbot", 60)


    # [공통] 멘션 삭제 & 타이머 갱신
    async def handle_success(self, guild_id, bot_type, cooldown_minutes):
        res = self.supabase.table("server_settings").select("*").eq("guild_id", guild_id).execute()
        if not res.data: return
        settings = res.data[0]

        # 봇 타입에 맞는 채널 ID 가져오기
        channel_id = settings.get(f"{bot_type}_channel_id")
        msg_id_col = f"{bot_type}_msg_id"
        next_at_col = f"{bot_type}_next_at"
        
        # 기존 알림 삭제
        old_msg_id = settings.get(msg_id_col)
        if channel_id and old_msg_id:
            try:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    old_msg = await channel.fetch_message(old_msg_id)
                    await old_msg.delete()
            except: pass

        # 시간 갱신
        next_time = datetime.now(timezone.utc) + timedelta(minutes=cooldown_minutes)
        self.supabase.table("server_settings").update({
            msg_id_col: None,
            next_at_col: next_time.isoformat()
        }).eq("guild_id", guild_id).execute()
        
        print(f"⏰ {bot_type} 갱신 완료 (Guild: {guild_id})")


    # ==========================================
    # 3. [자동 루프] 알림 전송
    # ==========================================
    @tasks.loop(seconds=60)
    async def bump_check_loop(self):
        await self.bot.wait_until_ready()

        res = self.supabase.table("server_settings").select("*").execute()
        if not res.data: return

        now = datetime.now(timezone.utc)

        for settings in res.data:
            guild_id = settings['guild_id']
            
            # 각각의 설정 가져오기
            disboard_role_id = settings.get('disboard_role_id')
            disboard_channel_id = settings.get('disboard_channel_id')
            
            koreanbot_role_id = settings.get('koreanbot_role_id')
            koreanbot_channel_id = settings.get('koreanbot_channel_id')

            # 디스보드 체크
            if disboard_role_id and disboard_channel_id:
                await self.check_and_send(settings, guild_id, disboard_channel_id, disboard_role_id, "disboard", now)
            
            # 코리안봇 체크
            if koreanbot_role_id and koreanbot_channel_id:
                await self.check_and_send(settings, guild_id, koreanbot_channel_id, koreanbot_role_id, "koreanbot", now)


    async def check_and_send(self, settings, guild_id, channel_id, role_id, bot_type, now):
        next_at_str = settings.get(f"{bot_type}_next_at")
        current_msg_id = settings.get(f"{bot_type}_msg_id")

        if next_at_str and current_msg_id is None:
            next_at = datetime.fromisoformat(next_at_str.replace('Z', '+00:00'))
            
            if now >= next_at:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    try:
                        msg = await channel.send(f"<@&{role_id}>")
                        
                        self.supabase.table("server_settings").update({
                            f"{bot_type}_msg_id": msg.id
                        }).eq("guild_id", guild_id).execute()
                    except Exception as e:
                        print(f"⚠️ 알림 전송 실패 ({bot_type}, {guild_id}): {e}")

async def setup(bot):
    await bot.add_cog(BumpCog(bot))
