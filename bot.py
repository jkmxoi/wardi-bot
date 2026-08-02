import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, time
import aiosqlite
import os
import pytz
from pathlib import Path
import random

# ========== الإعدادات ==========
TOKEN = os.getenv("DISCORD_TOKEN")
DB_PATH = "database/wardi.db"
PAGES_DIR = "quran_pages"

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ========== قاعدة البيانات ==========
async def init_db():
    os.makedirs("database", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                discord_id INTEGER PRIMARY KEY,
                current_page INTEGER DEFAULT 1,
                enabled BOOLEAN DEFAULT 1,
                send_time TEXT DEFAULT '07:00',
                last_read TIMESTAMP,
                khatmah_count INTEGER DEFAULT 0,
                streak_days INTEGER DEFAULT 0,
                longest_streak INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guilds (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER,
                timezone TEXT DEFAULT 'Asia/Riyadh',
                daily_message BOOLEAN DEFAULT 1,
                reminder_time TEXT DEFAULT '07:00'
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS khatmah (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                end_date TIMESTAMP,
                pages_read INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active'
            )
        """)
        await db.commit()

# ========== دالة إرسال الورد اليومي ==========
async def send_daily_ward(user: discord.User, page_num: int):
    """إرسال الورد اليومي مع زر أتممت القراءة فقط"""
    
    possible_exts = ['.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG']
    page_file = None
    actual_ext = '.jpg'
    
    for ext in possible_exts:
        candidate = f"{PAGES_DIR}/{page_num:03d}{ext}"
        if os.path.exists(candidate):
            page_file = candidate
            actual_ext = ext
            break
    
    if not page_file:
        await user.send(f"❌ عذراً، لم أجد صفحة رقم {page_num}. تأكدي من وجود صور المصحف في مجلد quran_pages/")
        return
    
    juz = ((page_num - 1) // 20) + 1
    hizb = ((page_num - 1) // 8) + 1
    
    embed = discord.Embed(
        title=f"🌸 ورد اليوم — الصفحة {page_num}",
        description=f"الجزء {juz} | الحزب {hizb}",
        color=0xFF69B4
    )
    embed.set_footer(text="وردي — اجعل لك ورداً من القرآن")
    
    file = discord.File(page_file, filename=f"page_{page_num:03d}{actual_ext}")
    embed.set_image(url=f"attachment://page_{page_num:03d}{actual_ext}")
    
    # زر واحد فقط: أتممت القراءة
    view = discord.ui.View()
    view.add_item(discord.ui.Button(
        label="✅ أتممت القراءة",
        style=discord.ButtonStyle.success,
        custom_id=f"done_{user.id}_{page_num}"
    ))
    
    await user.send(embed=embed, file=file, view=view)

# ========== دالة إرسال خيارات بعد القراءة ==========
async def send_options(user: discord.User, page_num: int):
    """إرسال خيارات بعد ما يكمل القراءة مع صورة maram.PNG"""
    
    # نبحث عن صورة maram.PNG في مجلد الصفحات
    possible_names = ['maram.PNG', 'maram.png', 'maram.jpg', 'maram.JPG', 'maram.jpeg']
    maram_file = None
    maram_ext = '.png'
    
    for name in possible_names:
        candidate = f"{PAGES_DIR}/{name}"
        if os.path.exists(candidate):
            maram_file = candidate
            maram_ext = os.path.splitext(name)[1]
            break
    
    embed = discord.Embed(
        title="🌸 ماذا تريد أن تفعل الآن؟",
        description=f"لقد أكملت صفحة {page_num}، بارك الله فيك!",
        color=0xFF69B4
    )
    embed.set_footer(text="وردي — استمر في الخير")
    
    view = discord.ui.View()
    
    view.add_item(discord.ui.Button(
        label="🤲 دعاء",
        style=discord.ButtonStyle.primary,
        custom_id=f"dua_{user.id}_{page_num}"
    ))
    
    view.add_item(discord.ui.Button(
        label="🔄 إعادة الصفحة",
        style=discord.ButtonStyle.secondary,
        custom_id=f"resend_{user.id}_{page_num}"
    ))
    
    view.add_item(discord.ui.Button(
        label="📖 الصفحة التالية",
        style=discord.ButtonStyle.success,
        custom_id=f"next_{user.id}_{page_num}"
    ))
    
    # إذا لقينا صورة maram نرسلها مع الرسالة
    if maram_file:
        file = discord.File(maram_file, filename=f"maram{maram_ext}")
        embed.set_image(url=f"attachment://maram{maram_ext}")
        await user.send(embed=embed, file=file, view=view)
    else:
        # إذا ما لقينا الصورة نرسل الرسالة بدون صورة
        await user.send(embed=embed, view=view)

# ========== الأوامر ==========
@bot.tree.command(name="ابدأ", description="اشترك في الورد اليومي أو استأنف قراءتك")
async def start_command(interaction: discord.Interaction):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT current_page, enabled FROM users WHERE discord_id = ?", 
            (interaction.user.id,)
        ) as cursor:
            row = await cursor.fetchone()
        
        if row:
            current_page, enabled = row
            if enabled == 0:
                await db.execute(
                    "UPDATE users SET enabled = 1 WHERE discord_id = ?",
                    (interaction.user.id,)
                )
                await db.commit()
            
            await interaction.response.send_message("📖 هذي صفحتك الحالية:", ephemeral=True)
            await send_daily_ward(interaction.user, current_page)
        else:
            await db.execute("""
                INSERT INTO users (discord_id, current_page, enabled, created_at)
                VALUES (?, 1, 1, CURRENT_TIMESTAMP)
            """, (interaction.user.id,))
            await db.commit()
            
            embed = discord.Embed(
                title="🌸 أهلاً بك في وردي!",
                description="تم تفعيل اشتراكك بنجاح. سوف يصلك ورد يومي في الرسائل الخاصة.",
                color=0xFF69B4
            )
            embed.add_field(name="📖 صفحتك الحالية", value="الصفحة 1 (الفاتحة)", inline=True)
            embed.add_field(name="⏰ وقت الإرسال", value="7:00 صباحاً", inline=True)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            await send_daily_ward(interaction.user, 1)

@bot.tree.command(name="إيقاف", description="إيقاف الورد اليومي")
async def stop_command(interaction: discord.Interaction):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET enabled = 0 WHERE discord_id = ?", (interaction.user.id,))
        await db.commit()
    await interaction.response.send_message("✅ تم إيقاف الورد اليومي. يمكنك العودة في أي وقت بكتابة `/ابدأ`", ephemeral=True)

@bot.tree.command(name="تقدمي", description="معرفة تقدمك في القراءة")
async def progress_command(interaction: discord.Interaction):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT current_page, khatmah_count, streak_days FROM users WHERE discord_id = ?", (interaction.user.id,)) as cursor:
            row = await cursor.fetchone()
    
    if not row:
        await interaction.response.send_message("❌ أنت غير مشترك. اكتب `/ابدأ` للاشتراك", ephemeral=True)
        return
    
    page, khatmah, streak = row
    progress = (page / 600) * 100
    
    embed = discord.Embed(title="📊 تقدمك", color=0xFF69B4)
    embed.add_field(name="الصفحة الحالية", value=f"{page}/600", inline=True)
    embed.add_field(name="الختمات المكتملة", value=str(khatmah), inline=True)
    embed.add_field(name="🔥 أيام الاستمرارية", value=f"{streak} يوم", inline=True)
    embed.add_field(name="نسبة التقدم", value=f"{progress:.1f}%", inline=False)
    
    filled = int(progress / 5)
    bar = "█" * filled + "░" * (20 - filled)
    embed.add_field(name="الشريط", value=f"`{bar}`", inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ========== أوامر الإدارة ==========
@bot.tree.command(name="set-channel", description="تحديد قناة التذكير (للأدمن فقط)")
@app_commands.describe(channel="القناة المطلوبة")
async def set_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ هذا الأمر للأدمن فقط", ephemeral=True)
        return
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO guilds (guild_id, channel_id)
            VALUES (?, ?)
        """, (interaction.guild_id, channel.id))
        await db.commit()
    
    await interaction.response.send_message(f"✅ تم تحديد قناة التذكير: {channel.mention}")

@bot.tree.command(name="set-time", description="تحديد وقت التذكير (للأدمن فقط)")
@app_commands.describe(hour="الساعة (0-23)", minute="الدقيقة (0-59)")
async def set_time(interaction: discord.Interaction, hour: int, minute: int):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ هذا الأمر للأدمن فقط", ephemeral=True)
        return
    
    time_str = f"{hour:02d}:{minute:02d}"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE guilds SET reminder_time = ? WHERE guild_id = ?", (time_str, interaction.guild_id))
        await db.commit()
    
    await interaction.response.send_message(f"✅ تم تحديد وقت التذكير: {time_str}")

@bot.tree.command(name="stats", description="إحصائيات السيرفر (للأدمن فقط)")
async def stats_command(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ هذا الأمر للأدمن فقط", ephemeral=True)
        return
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users WHERE enabled = 1") as cursor:
            total = (await cursor.fetchone())[0]
        async with db.execute("SELECT SUM(khatmah_count) FROM users") as cursor:
            khatmah_total = (await cursor.fetchone())[0] or 0
    
    embed = discord.Embed(title="📈 إحصائيات وردي", color=0xFF69B4)
    embed.add_field(name="👥 المشتركين النشطين", value=str(total), inline=True)
    embed.add_field(name="📚 إجمالي الختمات", value=str(khatmah_total), inline=True)
    await interaction.response.send_message(embed=embed)

# ========== معالجة الأزرار ==========
@bot.event
async def on_interaction(interaction: discord.Interaction):
    if not interaction.type == discord.InteractionType.component:
        return
    
    custom_id = interaction.data.get("custom_id", "")
    
    # ========== زر "أتممت القراءة" ==========
    if custom_id.startswith("done_"):
        parts = custom_id.split("_")
        user_id = int(parts[1])
        page_num = int(parts[2])
        
        if interaction.user.id != user_id:
            await interaction.response.send_message("❌ هذا الزر ليس لك", ephemeral=True)
            return
        
        # نحفظ التقدم
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT last_read, streak_days, current_page FROM users WHERE discord_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
            
            last_read, streak, current_page = row
            today = datetime.now().date()
            
            new_streak = streak + 1
            if last_read:
                try:
                    last_date = datetime.strptime(last_read.split()[0], "%Y-%m-%d").date()
                    if (today - last_date).days > 1:
                        new_streak = 1
                except:
                    new_streak = 1
            
            new_page = current_page + 1
            new_khatmah = 0
            
            if new_page > 600:
                new_page = 1
                new_khatmah = 1
            
            await db.execute("""
                UPDATE users SET 
                    current_page = ?,
                    last_read = CURRENT_TIMESTAMP,
                    streak_days = ?,
                    longest_streak = MAX(longest_streak, ?),
                    khatmah_count = khatmah_count + ?
                WHERE discord_id = ?
            """, (new_page, new_streak, new_streak, new_khatmah, user_id))
            await db.commit()
        
        # رسائل تشجيعية
        messages = {
            7: "🎉 أسبوع كامل! بارك الله فيك",
            30: "🌟 شهر كامل! استمر يا بطل",
            100: "💎 100 يوم! هذا إنجاز عظيم",
            365: "👑 سنة كاملة! أنت قدوة للجميع"
        }
        
        msg = "✅ تم حفظ تقدمك! "
        if new_streak in messages:
            msg += messages[new_streak]
        
        await interaction.response.send_message(msg, ephemeral=True)
        
        # نرسل خيارات بعد القراءة
        await send_options(interaction.user, page_num)
    
    # ========== زر "الصفحة التالية" ==========
    elif custom_id.startswith("next_"):
        parts = custom_id.split("_")
        user_id = int(parts[1])
        page_num = int(parts[2])
        
        if interaction.user.id != user_id:
            await interaction.response.send_message("❌ هذا الزر ليس لك", ephemeral=True)
            return
        
        # نجيب الصفحة الحالية من قاعدة البيانات
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT current_page FROM users WHERE discord_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                current_page = row[0] if row else 1
        
        await interaction.response.send_message("📖 هذي صفحتك الحالية:", ephemeral=True)
        await send_daily_ward(interaction.user, current_page)
    
    # ========== زر "إعادة الصفحة" ==========
    elif custom_id.startswith("resend_"):
        parts = custom_id.split("_")
        user_id = int(parts[1])
        page_num = int(parts[2])
        
        if interaction.user.id != user_id:
            await interaction.response.send_message("❌ هذا الزر ليس لك", ephemeral=True)
            return
        
        await interaction.response.send_message("📖 جاري إعادة إرسال الصفحة...", ephemeral=True)
        await send_daily_ward(interaction.user, page_num)
    
    # ========== زر "دعاء" ==========
    elif custom_id.startswith("dua_"):
        parts = custom_id.split("_")
        user_id = int(parts[1])
        page_num = int(parts[2])
        
        if interaction.user.id != user_id:
            await interaction.response.send_message("❌ هذا الزر ليس لك", ephemeral=True)
            return
        
        duas = [
            " اللهم اجعل القرآن ربيع قلبي ونور صدري وجلاء حزني وذهاب همي",
            " اللهم ذكرني منه ما نسيت وعلمني منه ما جهلت",
            " اللهم اجعلني من أهل القرآن الذين هم أهلك وخاصتك",
            " اللهم اجعل القرآن العظيم لي إماماً ونوراً وهدىً ورحمة"
        ]
        await interaction.response.send_message(random.choice(duas), ephemeral=True)

# ========== التذكير اليومي ==========
@tasks.loop(minutes=1)
async def daily_reminder():
    now = datetime.now(pytz.UTC)
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT discord_id, current_page, send_time 
            FROM users 
            WHERE enabled = 1
        """) as cursor:
            async for row in cursor:
                user_id, page, send_time = row
                try:
                    user_time = datetime.strptime(send_time, "%H:%M").time()
                    if now.hour == user_time.hour and now.minute == user_time.minute:
                        user = await bot.fetch_user(user_id)
                        if user:
                            await send_daily_ward(user, page)
                except:
                    continue
        
        async with db.execute("""
            SELECT guild_id, channel_id, reminder_time, timezone 
            FROM guilds 
            WHERE daily_message = 1 AND channel_id IS NOT NULL
        """) as cursor:
            async for row in cursor:
                guild_id, channel_id, reminder_time, tz = row
                try:
                    tz = pytz.timezone(tz or "Asia/Riyadh")
                    local_now = now.astimezone(tz)
                    rem_time = datetime.strptime(reminder_time, "%H:%M").time()
                    
                    if local_now.hour == rem_time.hour and local_now.minute == rem_time.minute:
                        channel = bot.get_channel(channel_id)
                        if channel:
                            embed = discord.Embed(
                                title="🌸 ورد اليوم",
                                description=(
                                    "﴿ وَلَقَدْ يَسَّرْنَا الْقُرْآنَ لِلذِّكْرِ فَهَلْ مِن مُّدَّكِرٍ ﴾\n\n"
                                    "📖 اجعل لك وردًا من القرآن، ولو صفحة واحدة.\n\n"
                                    "💌 للاشتراك في الورد اليومي اكتب: `/ابدأ`"
                                ),
                                color=0x7FD8FF
                            )
                            embed.set_footer(
                                text="وردي | رفيقك اليومي مع القرآن 🤍"
                            )
                            await channel.send(
                                embed=embed,
                                content="\n@everyone",
                                allowed_mentions=discord.AllowedMentions(everyone=True)
                            )
                except:
                    continue

@daily_reminder.before_loop
async def before_reminder():
    await bot.wait_until_ready()

# ========== الأحداث ==========
@bot.event
async def on_ready():
    print(f"✅ {bot.user} جاهز!")
    await init_db()
    await bot.tree.sync()
    print("✅ تم مزامنة الأوامر")
    if not daily_reminder.is_running():
        daily_reminder.start()

# ========== التشغيل ==========
if __name__ == "__main__":
    bot.run(TOKEN)