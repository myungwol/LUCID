import discord
from discord import app_commands
from discord.ext import commands
from discord import ui

# 1. [입력창 만들기] 팝업으로 뜰 모달창 정의
class EmbedModal(ui.Modal):
    def __init__(self, target_channel: discord.TextChannel, bot_user, edit_msg: discord.Message = None):
        # 모달창 제목 설정
        title_text = "임베드 패널 작성" if edit_msg is None else "임베드 패널 수정"
        super().__init__(title=title_text)
        
        self.target_channel = target_channel
        self.bot_user = bot_user
        self.edit_msg = edit_msg

        # 입력 항목들 추가
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
            # 색상은 텍스트로 복원하기 어려워서 패스

        self.add_item(self.embed_title)
        self.add_item(self.embed_content)
        self.add_item(self.embed_color)
        self.add_item(self.embed_image)

    # 색상 변환 함수
    def get_color(self, color_str: str):
        color_map = {
            "빨강": discord.Color.red(), "red": discord.Color.red(),
            "파랑": discord.Color.blue(), "blue": discord.Color.blue(),
            "초록": discord.Color.green(), "green": discord.Color.green(),
            "노랑": discord.Color.gold(), "yellow": discord.Color.gold(),
            "검정": discord.Color.default(), "black": discord.Color.default(),
            "보라": discord.Color.purple(), "purple": discord.Color.purple(),
        }
        
        # 1. 한글/영어 이름 확인
        if color_str in color_map:
            return color_map[color_str]
        
        # 2. 헥사 코드 (#FFFFFF) 확인
        if color_str.startswith("#"):
            try:
                return discord.Color.from_str(color_str)
            except:
                pass
        
        return discord.Color.brand_green() # 기본값

    # [전송 버튼] 눌렀을 때 실행되는 함수
    async def on_submit(self, interaction: discord.Interaction):
        # 임베드 만들기
        color = self.get_color(self.embed_color.value.strip())
        embed = discord.Embed(description=self.embed_content.value, color=color)
        
        # 제목이 있을 때만 설정
        if self.embed_title.value.strip():
            embed.title = self.embed_title.value
            
        # 이미지가 있을 때만 설정
        if self.embed_image.value.strip():
            embed.set_image(url=self.embed_image.value)

        embed.set_footer(text=f"작성자: {interaction.user.name}", icon_url=interaction.user.display_avatar.url)

        try:
            if self.edit_msg:
                # 수정 모드
                await self.edit_msg.edit(embed=embed)
                await interaction.response.send_message("✅ 패널이 수정되었습니다!", ephemeral=True)
            else:
                # 작성 모드
                await self.target_channel.send(embed=embed)
                await interaction.response.send_message(f"✅ {self.target_channel.mention} 채널에 패널을 보냈습니다!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 오류 발생: {e}", ephemeral=True)


# 2. [명령어 연결] Cogs 클래스
class EmbedCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="패널작성", description="입력창을 띄워 깔끔한 임베드 패널을 작성합니다.")
    @app_commands.describe(channel="패널을 보낼 채널")
    @app_commands.checks.has_permissions(administrator=True)
    async def create_panel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        # 모달창 띄우기
        await interaction.response.send_modal(EmbedModal(target_channel=channel, bot_user=self.bot.user))

    @app_commands.command(name="패널수정", description="기존 패널 내용을 수정합니다.")
    @app_commands.describe(channel="채널 선택", message_id="수정할 메시지 ID")
    @app_commands.checks.has_permissions(administrator=True)
    async def edit_panel(self, interaction: discord.Interaction, channel: discord.TextChannel, message_id: str):
        try:
            msg = await channel.fetch_message(int(message_id))
            if msg.author != self.bot.user:
                await interaction.response.send_message("❌ 제가 보낸 메시지만 수정할 수 있습니다.", ephemeral=True)
                return
            
            # 모달창 띄우기 (기존 메시지 정보를 같이 넘김)
            await interaction.response.send_modal(EmbedModal(target_channel=channel, bot_user=self.bot.user, edit_msg=msg))
            
        except discord.NotFound:
            await interaction.response.send_message("❌ 해당 메시지를 찾을 수 없습니다. ID를 확인해주세요.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 오류 발생: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(EmbedCog(bot))
