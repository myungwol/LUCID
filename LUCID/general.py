import discord
from discord import app_commands
from discord.ext import commands

class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="청소", description="지정한 개수만큼 메시지를 삭제합니다.")
    @app_commands.describe(amount="삭제할 메시지의 개수")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clear_chat(self, interaction: discord.Interaction, amount: int):
        if amount < 1:
            await interaction.response.send_message("1개 이상의 숫자를 입력해주세요.", ephemeral=True)
            return

        await interaction.response.send_message(f"{amount}개의 메시지를 삭제 중입니다...", ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.edit_original_response(content=f"🧹 **{len(deleted)}개**의 메시지를 깨끗하게 청소했습니다!")

    # 에러 처리
    @clear_chat.error
    async def clear_chat_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ 관리 권한이 없습니다.", ephemeral=True)

# 봇이 이 파일을 불러올 때 실행되는 함수
async def setup(bot):
    await bot.add_cog(General(bot))
