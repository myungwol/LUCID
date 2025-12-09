import discord
from discord import app_commands
from discord.ext import commands

class EmbedCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # 색상 변환 도우미 함수 (간단하게 몇 가지만 지원)
    def get_color(self, color_str: str):
        if color_str == "빨강": return discord.Color.red()
        if color_str == "파랑": return discord.Color.blue()
        if color_str == "초록": return discord.Color.green()
        if color_str == "노랑": return discord.Color.gold()
        if color_str == "검정": return discord.Color.default()
        return discord.Color.brand_green() # 기본값

    # 1. [임베드 보내기]
    @app_commands.command(name="공지작성", description="멋진 임베드 메시지를 보냅니다.")
    @app_commands.describe(
        channel="메시지를 보낼 채널",
        title="공지 제목",
        content="공지 내용 (줄바꿈 가능)",
        color="색상 (빨강, 파랑, 초록, 노랑, 검정 중 택1)"
    )
    @app_commands.checks.has_permissions(administrator=True) # 관리자만 사용 가능
    async def send_embed(self, interaction: discord.Interaction, channel: discord.TextChannel, title: str, content: str, color: str = None):
        
        # 색상 설정
        embed_color = self.get_color(color)
        
        # 임베드 만들기
        embed = discord.Embed(title=title, description=content, color=embed_color)
        embed.set_footer(text=f"작성자: {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
        
        # 해당 채널로 전송
        await channel.send(embed=embed)
        
        # 나한테만 성공 메시지 보냄
        await interaction.response.send_message(f"✅ {channel.mention} 채널에 공지를 등록했습니다!", ephemeral=True)

    # 2. [임베드 수정하기]
    @app_commands.command(name="공지수정", description="기존에 보낸 임베드 내용을 수정합니다.")
    @app_commands.describe(
        channel="수정할 메시지가 있는 채널",
        message_id="수정할 메시지의 ID (우클릭 -> ID 복사하기)",
        new_title="새로운 제목",
        new_content="새로운 내용"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def edit_embed(self, interaction: discord.Interaction, channel: discord.TextChannel, message_id: str, new_title: str, new_content: str):
        try:
            # 메시지 찾아오기
            msg = await channel.fetch_message(int(message_id))
            
            # 봇이 보낸 메시지가 맞는지 확인
            if msg.author != self.bot.user:
                await interaction.response.send_message("❌ 제가 보낸 메시지만 수정할 수 있어요.", ephemeral=True)
                return

            # 기존 색상은 유지하고 내용만 바꿈
            original_color = msg.embeds[0].color if msg.embeds else discord.Color.brand_green()
            
            # 새 임베드 생성
            new_embed = discord.Embed(title=new_title, description=new_content, color=original_color)
            new_embed.set_footer(text=f"수정됨: {interaction.user.name}", icon_url=interaction.user.display_avatar.url)

            # 수정 적용
            await msg.edit(embed=new_embed)
            await interaction.response.send_message("✅ 공지사항을 수정했습니다!", ephemeral=True)

        except discord.NotFound:
            await interaction.response.send_message("❌ 해당 ID의 메시지를 찾을 수 없습니다.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 오류가 발생했습니다: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(EmbedCog(bot))
