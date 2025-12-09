import discord
from discord import app_commands
from discord.ext import commands
from discord import ui

# 1. [팝업창] 모달 정의 (이전과 동일)
class EmbedModal(ui.Modal):
    def __init__(self, target_channel: discord.TextChannel, bot_user, edit_msg: discord.Message = None):
        title_text = "임베드 패널 작성" if edit_msg is None else "임베드 패널 수정"
        super().__init__(title=title_text)
        
        self.target_channel = target_channel
        self.bot_user = bot_user
        self.edit_msg = edit_msg

        self.embed_title = ui.TextInput(
            label="제목 (비워두면 제목 없음)", 
            placeholder="제목을 입력하세요 (선택사항)", 
            required=False
        )
        self.embed_content = ui.TextInput(
            label="내용", 
            placeholder="내용을 입력하세요. (엔터로 줄바꿈 가능)", 
            style=discord.TextStyle.paragraph, 
            required=True
        )
        self.embed_color = ui.TextInput(
            label="색상 (예: 빨강, 파랑, #FF0000)", 
            placeholder="비워두면 기본색 적용",
            required=False
        )
        self.embed_image = ui.TextInput(
            label="이미지 URL (선택)", 
            placeholder="https://...", 
            required=False
        )

        if edit_msg and edit_msg.embeds:
            og_embed = edit_msg.embeds[0]
            if og_embed.title: self.embed_title.default = og_embed.title
            if og_embed.description: self.embed_content.default = og_embed.description
            if og_embed.image: self.embed_image.default = og_embed.image.url

        self.add_item(self.embed_title)
        self.add_item(self.embed_content)
        self.add_item(self.embed_color)
        self.add_item(self.embed_image)

    def get_color(self, color_str: str):
        color_map = {
            "빨강": discord.Color.red(), "red": discord.Color.red(),
            "파랑": discord.Color.blue(), "blue": discord.Color.blue(),
            "초록": discord.Color.green(), "green": discord.Color.green(),
            "노랑": discord.Color.gold(), "yellow": discord.Color.gold(),
            "검정": discord.Color.default(), "black": discord.Color.default(),
            "보라": discord.Color.purple(), "purple": discord.Color.purple(),
            "흰색": discord.Color.from_rgb(255, 255, 255), "white": discord.Color.from_rgb(255, 255, 255),
        }
        
        if color_str in color_map: return color_map[color_str]
        if color_str.startswith("#"):
            try: return discord.Color.from_str(color_str)
            except: pass
        return discord.Color.brand_green()

    async def on_submit(self, interaction: discord.Interaction):
        color = self.get_color(self.embed_color.value.strip())
        embed = discord.Embed(description=self.embed_content.value, color=color)
        
        if self.embed_title.value.strip():
            embed.title = self.embed_title.value
        if self.embed_image.value.strip():
            embed.set_image(url=self.embed_image.value)

        try:
            if self.edit_msg:
                await self.edit_msg.edit(embed=embed)
                await interaction.response.send_message("✅ 패널이 수정되었습니다!", ephemeral=True)
            else:
                await self.target_channel.send(embed=embed)
                await interaction.response.send_message(f"✅ {self.target_channel.mention} 채널에 패널을 보냈습니다!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 오류 발생: {e}", ephemeral=True)


# 2. [Cogs] 명령어 및 컨텍스트 메뉴 연결 (수정된 부분 ⭐)
class EmbedCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        # [중요] Cog 안에서는 우클릭 메뉴를 이렇게 수동으로 등록해야 합니다.
        self.ctx_menu = app_commands.ContextMenu(
            name="패널 수정",
            callback=self.edit_panel_context,
        )
        self.bot.tree.add_command(self.ctx_menu)

    # 봇이 꺼지거나 리로드될 때 메뉴를 삭제해줌 (중복 방지)
    async def cog_unload(self):
        self.bot.tree.remove_command(self.ctx_menu.name, type=self.ctx_menu.type)

    # [슬래시 커맨드] 생성용
    @app_commands.command(name="패널작성", description="입력창을 띄워 깔끔한 임베드 패널을 작성합니다.")
    @app_commands.describe(channel="패널을 보낼 채널")
    @app_commands.checks.has_permissions(administrator=True)
    async def create_panel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await interaction.response.send_modal(EmbedModal(target_channel=channel, bot_user=self.bot.user))

    # [우클릭 메뉴 함수] (데코레이터 없이 함수만 정의)
    @app_commands.checks.has_permissions(administrator=True)
    async def edit_panel_context(self, interaction: discord.Interaction, message: discord.Message):
        if message.author != self.bot.user:
            await interaction.response.send_message("❌ 제가 보낸 메시지만 수정할 수 있습니다.", ephemeral=True)
            return

        await interaction.response.send_modal(EmbedModal(target_channel=interaction.channel, bot_user=self.bot.user, edit_msg=message))

async def setup(bot):
    await bot.add_cog(EmbedCog(bot))
