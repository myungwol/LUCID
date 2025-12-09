import discord
from discord import app_commands
from discord.ext import commands

class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="유저수", description="현재 서버의 멤버 수를 알려줍니다.")
    async def user_count(self, interaction: discord.Interaction):
        # interaction.guild가 현재 서버 정보를 담고 있습니다.
        guild = interaction.guild
        member_count = guild.member_count
        
        # 봇을 제외한 사람 수만 세고 싶다면 아래 코드를 씁니다 (옵션)
        # human_count = len([m for m in guild.members if not m.bot])

        embed = discord.Embed(title="📊 서버 현황", color=discord.Color.blue())
        embed.add_field(name="총 멤버 수", value=f"{member_count}명", inline=False)
        
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Stats(bot))
