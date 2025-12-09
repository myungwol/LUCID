import discord
from discord import app_commands
from discord.ext import commands
from discord import ui

# 1. [팝업창] 모달 정의 (이전과 동일)
class EmbedModal(ui.Modal):
    def __init__(self, target_channel: discord.TextChannel, bot_user, edit_msg: discord.Message = None):
        # 모달창 제목 설정
        title_text = "임베드 패널 작성" if edit_msg is None else "임베드 패널 수정"
        super().__init__(title=title_text)
        
        self.target_channel = target_channel
        self.bot_user = bot_user
        self.edit_msg = edit_msg

        # 입력 항목들
        self.embed_title = ui.TextInput(
            label="제목 (비워두면 제목 없음)", 
            placeholder="제목을 입력하세요 (선택사항)", 
            required=False
        )
        self.embed_content = ui.TextInput(
            label="내용", 
            placeholder="내용을 입력하세요. (엔터로 줄바꿈 가능)", 
            style=discord.TextStyle.paragraph, # 큰 입력창
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

        # 수정 모드일 경우, 기존 내용을 채워넣음
        if edit_msg and edit_msg.embeds:
            og_embed = edit_msg.embeds[0]
            if og_embed.title: self.embed_title.default = og_embed.title
            if og_embed.description: self.embed_content.default = og_embed.description
            if og_embed.image: self.embed_image.default = og_embed.image.url

        self.add_item(self.embed_title)
        self.add_item(self.embed_content)
        self.add_item(self.embed_color)
        self.add_item(self.embed_image)

    # 색상 변환
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

    # [전송/수정 버튼 클릭 시]
    async def on_submit(self, interaction: discord.Interaction):
        color = self.get_color(self.embed_color.value.strip())
        embed = discord.Embed(description=self.embed_content.value, color=color)
        
        if self.embed_title.value.strip():
            embed.title = self.embed_title.value
            
        if self.embed_image.value.strip():
            embed.set_image(url=self.embed_image.value)

        # 작성자(Footer) 없이 깔끔하게 전송

        try:
            if self.edit_msg:
                await self.edit_msg.edit(embed=embed)
                await interaction.response.send_message("✅ 패널이 수정되었습니다!", ephemeral=True)
            else:
                await self.target_channel.send(embed=embed)
                await interaction.response.send_message(f"✅ {self.target_channel.mention} 채널에 패널을 보냈습니다!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 오류 발생: {e}", ephemeral=True)


# 2. [Cogs] 명령어 및 컨텍스트 메뉴 연결
class EmbedCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # (1) 생성은 슬래시 커맨드로 유지 (/패널작성)
    @app_commands.command(name="패널작성", description="입력창을 띄워 깔끔한 임베드 패널을 작성합니다.")
    @app_commands.describe(channel="패널을 보낼 채널")
    @app_commands.checks.has_permissions(administrator=True)
    async def create_panel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await interaction.response.send_modal(EmbedModal(target_channel=channel, bot_user=self.bot.user))

    # (2) 수정은 우클릭 메뉴로 변경 (Context Menu)
    @app_commands.context_menu(name="패널 수정")
    @app_commands.checks.has_permissions(administrator=True)
    async def edit_panel_context(self, interaction: discord.Interaction, message: discord.Message):
        # 봇이 보낸 메시지인지 확인
        if message.author != self.bot.user:
            await interaction.response.send_message("❌ 제가 보낸 메시지만 수정할 수 있습니다.", ephemeral=True)
            return

        # 모달창 띄우기 (현재 채널, 봇, 대상 메시지 전달)
        await interaction.response.send_modal(EmbedModal(target_channel=interaction.channel, bot_user=self.bot.user, edit_msg=message))

async def setup(bot):
    await bot.add_cog(EmbedCog(bot))
