import discord
from discord.ext import commands
from discord import ButtonStyle
from discord.ui import Button, View
import json
import asyncio
from datetime import datetime
from flask import Flask
from threading import Thread
import os
from dotenv import load_dotenv
import os

load_dotenv()
TOKEN = os.getenv("TOKEN")  # Tokenı .env veya Render ortam değişkeninden al

if TOKEN is None:
    print("Token bulunamadı! .env dosyasını veya Render ortam değişkenini kontrol edin.")
    exit(1)

# Bot ayarları
1390373120761925762 = None  # Ticket kanallarının oluşturulacağı kategori ID
STAFF_ROLE_ID = None      # Yetkili rol ID

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Ticket verilerini saklamak için değişkenleri güncelle
ticket_data = {}
ticket_count = 0  # Ticket sayacı

# Log kanalının ID'sini buraya yaz (örnek: 123456789012345678)
TICKET_LOG_CHANNEL_ID = 1402105444704719060  # <-- kendi log kanalının ID'sini yaz

async def log_ticket_event(guild, user, channel, action):
    """Ticket açma/kapama olayını log kanalına gönderir."""
    log_channel = guild.get_channel(TICKET_LOG_CHANNEL_ID)
    if log_channel:
        if action == "açıldı":
            embed = discord.Embed(
                title="🎫 Yeni Ticket Açıldı",
                description=(
                    f"• Açan: {user.mention}\n"
                    f"• Kanal: {channel.mention}\n"
                    f"• Tarih: <t:{int(datetime.now().timestamp())}:F>"
                ),
                color=discord.Color.green()
            )
        elif action == "kapandı":
            embed = discord.Embed(
                title="❌ Ticket Kapatıldı",
                description=(
                    f"• Kapatan: {user.mention}\n"
                    f"• Kanal: {channel.name}\n"
                    f"• Tarih: <t:{int(datetime.now().timestamp())}:F>"
                ),
                color=discord.Color.red()
            )
        await log_channel.send(embed=embed)

# Log transcript fonksiyonunu ekleyin (import bölümünden sonra)
async def log_ticket_transcript(channel):
    """Ticket'ın konuşma geçmişini log kanalına gönderir."""
    try:
        log_channel = channel.guild.get_channel(TICKET_LOG_CHANNEL_ID)
        if not log_channel:
            return

        messages = []
        async for message in channel.history(limit=None, oldest_first=True):
            timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
            messages.append(f"{timestamp} - {message.author.name}: {message.content}")

        transcript = "\n".join(messages)
        
        # Dosya çok uzunsa, ilk 2000 karakteri al
        if len(transcript) > 2000:
            transcript = transcript[:1997] + "..."

        embed = discord.Embed(
            title=f"📝 Ticket Transcript - {channel.name}",
            description=f"```\n{transcript}\n```",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        await log_channel.send(embed=embed)
        
    except Exception as e:
        print(f"Transcript log hatası: {e}")

# Ticket açıldığında sadece dropdown gelsin, formu ve kapatma butonunu ticket açılırken gönderme!
class TicketView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Ticket Oluştur", style=ButtonStyle.green, custom_id="create_ticket")
    async def create_ticket(self, interaction: discord.Interaction, button: Button):
        global ticket_count
        guild = interaction.guild
        member = interaction.user
        
        # Kullanıcının aktif ticket'ı var mı kontrol et - tüm ticketları kontrol eder
        for channel in guild.channels:
            if channel.name.startswith("scorpion-ticket-"):
                ticket_info = ticket_data.get(channel.id, {})
                if ticket_info.get("owner_id") == member.id:
                    await interaction.response.send_message(
                        "⚠️ Zaten açık bir ticket'ınız var! Yeni ticket açmadan önce mevcut ticket'ınızı kapatmalısınız.", 
                        ephemeral=True
                    )
                    return
    
        # Ticket sayacını artır
        ticket_count += 1
        
        # Ticket kanalı oluştur
        channel = await guild.create_text_channel(
            name=f"scorpion-ticket-{ticket_count}",
            category=guild.get_channel(TICKET_CATEGORY_ID),
            topic=f"Ticket sahibi: {member.name} | Ticket ID: {ticket_count}"
        )
        
        # Kanal izinlerini ayarla
        await channel.set_permissions(guild.default_role, view_channel=False)
        await channel.set_permissions(member, view_channel=True, send_messages=True)
        
        # Staff role kontrolü ve izin ayarı
        staff_role = guild.get_role(STAFF_ROLE_ID)
        if staff_role:  # Eğer rol varsa
            await channel.set_permissions(staff_role, view_channel=True, send_messages=True)
        else:
            print(f"Uyarı: Staff rol ID'si ({STAFF_ROLE_ID}) için rol bulunamadı!")
        
        # Ticket verilerini kaydet
        ticket_data[channel.id] = {
            "owner_id": member.id,
            "ticket_number": ticket_count,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Ticket açıldıktan sonra sadece dropdown gönder!
        await channel.send("Lütfen ticket türünü seçin:", view=TicketTypeView())

        # Kullanıcıya ticket'ın oluşturulduğunu bildir
        await interaction.response.send_message(
            f"✅ Ticket oluşturuldu! {channel.mention}", 
            ephemeral=True
        )

        # Ticket açıldığında log kanalına bildir
        await log_ticket_event(guild, member, channel, "açıldı")

class CloseView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="❌ Ticket'ı Kapat", style=ButtonStyle.red, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: Button):
        channel = interaction.channel
        embed = discord.Embed(
            title="Ticket Kapatılıyor",
            description="Ticket 5 saniye içinde kapatılacak.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)
        await asyncio.sleep(5)
        # --- TRANSCRIPT LOG ---
        await log_ticket_transcript(channel)
        await channel.delete()
        if channel.id in ticket_data:
            del ticket_data[channel.id]
        await log_ticket_event(channel.guild, interaction.user, channel, "kapandı")

# Dropdown'u güncelle:
class TicketTypeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Ekip Başvuru", description="Ekip başvuru formunu doldur"),
            discord.SelectOption(label="Oyun İçi Sorunlar", description="Oyun içi sorunlar için ticket aç"),
            discord.SelectOption(label="Ekip İçi", description="Ekip içi destek için ticket aç"),
        ]
        super().__init__(placeholder="Ticket türünü seçin...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        channel = interaction.channel
        member = interaction.user

        # Dropdown'u devre dışı bırak
        self.disabled = True
        await interaction.message.edit(view=self.view)

        if self.values[0] == "Ekip Başvuru":
            embed = discord.Embed(
                title="🎫 Scorpion Başvuru Formu",
                description=(
                    f"Merhaba {member.mention}!\n"
                    "Lütfen aşağıdaki bilgileri eksiksiz doldurunuz.\n"
                    "**Not:** Cevaplarınızı tek bir mesajda yazınız.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "**1.** FiveM'de kaç saatiniz var?\n\n"
                    "**2.** 5 tane POV yazınız\n\n"
                    "**3.** MAP bilginiz nedir?\n\n"
                    "**4.** Hangi ekiplerde oynadınız?\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━"
                ),
                color=0x2b2d31
            )
            embed.set_footer(text="Cevaplarınız yetkili ekibimiz tarafından incelenecektir.")
            await channel.send(embed=embed)
        elif self.values[0] == "Oyun İçi Sorunlar":
            await channel.send(f"{member.mention} Oyun içi sorunlar için ticket açıldı. Yetkililer seninle ilgilenecek.")
        elif self.values[0] == "Ekip İçi":
            await channel.send(f"{member.mention} Ekip içi destek için ticket açıldı. Yetkililer seninle ilgilenecek.")

        # Kapatma butonu ekle
        await channel.send("İşleminiz tamamlandıysa aşağıdaki butonu kullanarak ticket'ı kapatabilirsiniz:", view=CloseView())
        await interaction.response.defer()

class TicketTypeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketTypeSelect())

@bot.event
async def on_ready():
    # Bot durumunu güncelle
    try:
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="Scorpion Manager"
            ),
            status=discord.Status.online
        )
        print(f"{bot.user.name} olarak giriş yapıldı!")
        print("Bot durumu 'Scorpion Manager' olarak ayarlandı!")
    except Exception as e:
        print(f"Hata: {e}")

@bot.command()
@commands.has_permissions(administrator=True)
async def ticket_panel(ctx):
    """Ticket oluşturma panelini gönderir"""
    embed = discord.Embed(
        title="🎫 Ticket Sistemi",
        description="Destek almak için aşağıdaki butona tıklayın.",
        color=discord.Color.blue()
    )
    
    view = TicketView()
    await ctx.send(embed=embed, view=view)

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        channel = interaction.channel
        if not channel.name.startswith("scorpion-ticket-"):
            return
            
        member = interaction.user
        staff_role = interaction.guild.get_role(STAFF_ROLE_ID)
        ticket_data_entry = ticket_data.get(channel.id, {})
        ticket_owner_id = ticket_data_entry.get("owner_id")

        if member.id != ticket_owner_id and staff_role not in member.roles:
            await interaction.response.send_message(
                "Bu işlemi yapmaya yetkiniz yok!", ephemeral=True)
            return

        if interaction.custom_id == "close_ticket":
            embed = discord.Embed(
                title="Ticket Kapatılıyor",
                description="Ticket 5 saniye içinde kapatılacak.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)
            await asyncio.sleep(5)
            
            # Kapatma butonunda:
            await log_ticket_transcript(channel)
            await channel.delete()
            if channel.id in ticket_data:
                del ticket_data[channel.id]

            # Ticket kapandığında log kanalına bildir
            await log_ticket_event(channel.guild, interaction.user, channel, "kapandı")

        elif interaction.custom_id == "lock_ticket":
            # Ticket'ı kilitle (kullanıcının yazma iznini kaldır)
            ticket_owner = interaction.guild.get_member(ticket_owner_id)
            await channel.set_permissions(ticket_owner, view_channel=True, send_messages=False)
            
            embed = discord.Embed(
                title="🔒 Ticket Kilitlendi",
                description="Bu ticket yetkili tarafından kilitlendi.",
                color=discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def setup_ticket(ctx, category_id: int, staff_role_id: int):
    """Ticket sistemini kurar"""
    global TICKET_CATEGORY_ID, STAFF_ROLE_ID
    
    # Kategori kontrolü
    category = ctx.guild.get_channel(category_id)
    if not category or not isinstance(category, discord.CategoryChannel):
        await ctx.send("❌ Geçersiz kategori ID'si!")
        return
    
    # Rol kontrolü
    staff_role = ctx.guild.get_role(staff_role_id)
    if not staff_role:
        await ctx.send("❌ Geçersiz rol ID'si!")
        return
    
    TICKET_CATEGORY_ID = category_id
    STAFF_ROLE_ID = 1401676238921404457
    
    await ctx.send(f"✅ Ticket sistemi başarıyla kuruldu!\nKategori: {category.name}\nYetkili Rolü: {staff_role.name}")

app = Flask('')
    
@app.route('/')
def home():
    return "Ticket Bot Aktif!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    server = Thread(target=run)
    server.start()

# Bot'u başlat
try:
    keep_alive()
    bot.run(TOKEN)
except Exception as e:
    print(f"Bot başlatma hatası: {e}")
