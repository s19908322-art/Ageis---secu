"""
╔══════════════════════════════════════════════╗
║       AEGIS SECURITY — Bot de Protection     ║
║  Anti-nuke • Anti-raid • Anti-spam • Modéra  ║
╚══════════════════════════════════════════════╝
Variable Railway : DISCORD_BOT_TOKEN_SECURITY
"""
import discord
from discord.ext import commands
from discord import app_commands
import os, logging, asyncio, random
from datetime import datetime, timezone, timedelta
from typing import Optional
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('AegisSecurity')

BOT_OWNER_ID = int(os.environ.get('BOT_OWNER_ID', '0'))

# ── Thème ──
class C:
    RED=0xFF0040; ORANGE=0xFF6600; BLUE=0x0080FF; GREEN=0x00FF41
    PINK=0xFF00FF; CYAN=0x00FFFF; GOLD=0xFFD700; DARK=0x0D0D0D

def emb(title, desc=None, color=C.CYAN, footer=None):
    e = discord.Embed(title=title, description=desc, color=color, timestamp=datetime.now(timezone.utc))
    e.set_footer(text=footer or "AEGIS SECURITY  ◈  discord.gg/6rN8pneGdy")
    return e

def ok(t, d=None):   return emb(f"✅  {t}", d, C.GREEN)
def er(t, d=None):   return emb(f"❌  {t}", d, C.RED)
def inf(t, d=None):  return emb(f"◈  {t}", d, C.CYAN)
def wrn(t, d=None):  return emb(f"⚠️  {t}", d, C.ORANGE)

def can_target(actor: discord.Member, target: discord.Member) -> bool:
    if not actor or not target: return False
    if target.id == actor.guild.owner_id: return False
    if target.id == actor.guild.me.id: return False
    ar = getattr(actor, 'top_role', None)
    tr = getattr(target, 'top_role', None)
    if ar is None or tr is None: return True
    return ar > tr

def default_raid(): return {"enabled": True, "threshold": 5, "action": "kick"}
def default_spam(): return {"enabled": True, "limit": 5, "window": 5, "mentions": 5, "action": "mute", "dur": 5}
def default_nuke(): return {"enabled": True, "threshold": 5, "action": "kick", "whitelist": []}

# ── Bot ──
intents = discord.Intents.all()

class AegisSecurity(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!sec_', intents=intents, help_command=None)
        self.warnings    = {}
        self.logs_ch     = {}
        self.raid_cfg    = {}
        self.raid_cache  = {}
        self.spam_cfg    = {}
        self.nuke_cfg    = {}
        self.nuke_track  = {}
        self.msg_cache   = defaultdict(list)
        self._join_cache = {}
        self._rem_cache  = {}

    async def setup_hook(self):
        try:
            n = await self.tree.sync()
            logger.info(f"✅ {len(n)} commandes sync")
        except Exception as e:
            logger.error(f"Sync: {e}")

bot = AegisSecurity()

@bot.tree.error
async def on_error(i: discord.Interaction, error: app_commands.AppCommandError):
    e = er("Erreur", f"`{str(error)[:200]}`")
    try:
        if i.response.is_done(): await i.followup.send(embed=e, ephemeral=True)
        else: await i.response.send_message(embed=e, ephemeral=True)
    except: pass

async def log(guild, title, desc, color=C.CYAN):
    gid = str(guild.id)
    if gid in bot.logs_ch:
        ch = guild.get_channel(bot.logs_ch[gid])
        if ch:
            try: await ch.send(embed=emb(f"◈  {title}", desc, color))
            except: pass

# ── Anti-spam ──
async def check_spam(msg: discord.Message) -> bool:
    if msg.author.bot or msg.author.guild_permissions.administrator: return False
    gid = str(msg.guild.id); uid = msg.author.id; now = datetime.now(timezone.utc)
    cfg = bot.spam_cfg.get(gid) or default_spam()
    if not cfg.get("enabled", True): return False
    bot.msg_cache[uid].append(now)
    bot.msg_cache[uid] = [t for t in bot.msg_cache[uid] if (now-t).total_seconds() < cfg["window"]]
    spam = False; reason = ""
    if len(bot.msg_cache[uid]) > cfg["limit"]: spam = True; reason = "Spam messages"
    ments = len(msg.mentions) + len(msg.role_mentions) + (50 if msg.mention_everyone else 0)
    if ments >= cfg["mentions"]: spam = True; reason = f"Spam mentions ({ments})"
    if spam:
        try:
            await msg.delete()
            a = cfg["action"]
            if   a == "kick": await msg.author.kick(reason=reason)
            elif a == "ban":  await msg.author.ban(reason=reason)
            else: await msg.author.timeout(now + timedelta(minutes=cfg["dur"]), reason=reason)
            await msg.channel.send(embed=wrn("Anti-Spam", f"{msg.author.mention} sanctionné — {reason}"), delete_after=8)
            bot.msg_cache[uid] = []
            return True
        except: pass
    return False

# ── Anti-nuke ──
async def nuke_check(guild: discord.Guild, uid: int, action: str):
    gid = str(guild.id)
    cfg = bot.nuke_cfg.get(gid) or default_nuke()
    if not cfg.get("enabled", True): return
    if uid == guild.owner_id: return
    if uid in cfg.get("whitelist", []): return
    if uid == BOT_OWNER_ID: return
    now = datetime.now(timezone.utc)
    tr  = bot.nuke_track.setdefault(gid, {})
    ud  = tr.setdefault(str(uid), {})
    last = ud.get("t")
    if not last or (now - last).total_seconds() > 10: ud.clear(); ud["t"] = now
    ud[action] = ud.get(action, 0) + 1
    total = sum(v for k, v in ud.items() if k != "t")
    if total >= cfg.get("threshold", 5):
        member = guild.get_member(uid)
        if member:
            try:
                reason = f"Anti-nuke: {total} actions/10s"
                if cfg.get("action") == "ban": await guild.ban(member, reason=reason)
                else: await guild.kick(member, reason=reason)
                desc = f"**Membre :** {member} (`{member.id}`)\n**Action :** {action} × {total}/10s\n**Sanction :** {cfg.get('action','kick')}"
                await log(guild, "☢️ Anti-Nuke", desc, C.RED)
                tr.pop(str(uid), None)
            except Exception as e: logger.error(f"nuke_check: {e}")

# ── Events ──
@bot.event
async def on_ready():
    logger.info(f"🛡️ AEGIS SECURITY en ligne | {len(bot.guilds)} serveurs")
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching, name="🛡️ Protection | AEGIS Security"))
    try:
        await bot.application.edit(description=(
            "🛡️ AEGIS SECURITY — Protection avancée\n\n"
            "Anti-nuke ◈ Anti-raid ◈ Anti-spam\n"
            "Modération complète ◈ Logs\n\n"
            "Support : https://discord.gg/6rN8pneGdy"
        ))
    except: pass

@bot.event
async def on_guild_join(guild: discord.Guild):
    gid = str(guild.id)
    bot.raid_cfg[gid] = default_raid()
    bot.spam_cfg[gid] = default_spam()
    bot.nuke_cfg[gid] = default_nuke()
    ch = guild.system_channel or next((c for c in guild.text_channels if c.permissions_for(guild.me).send_messages), None)
    if ch:
        e = discord.Embed(title="🛡️  AEGIS SECURITY — En ligne",
            description="Protection activée automatiquement :\n▸ Anti-raid ✅\n▸ Anti-spam ✅\n▸ Anti-nuke ✅\n\nUtilise `/antiraid` `/antispam` `/antinuke` pour configurer.",
            color=C.CYAN, timestamp=datetime.now(timezone.utc))
        try: await ch.send(embed=e)
        except: pass

@bot.event
async def on_member_join(member: discord.Member):
    gid = str(member.guild.id); now = datetime.now(timezone.utc)
    key = f"join-{gid}-{member.id}"
    last = bot._join_cache.get(key)
    if last and (now - last).total_seconds() < 30: return
    bot._join_cache[key] = now
    if len(bot._join_cache) > 500: bot._join_cache.clear()
    bot.raid_cache.setdefault(gid, []).append(now)
    bot.raid_cache[gid] = [t for t in bot.raid_cache[gid] if (now-t).total_seconds() < 10]
    raid = bot.raid_cfg.get(gid) or default_raid()
    if raid.get("enabled") and len(bot.raid_cache[gid]) > raid.get("threshold", 5):
        try:
            if raid.get("action") == "ban": await member.ban(reason="Anti-raid")
            else: await member.kick(reason="Anti-raid")
        except: pass

@bot.event
async def on_member_ban(guild, user):
    try:
        await asyncio.sleep(0.5)
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
            if entry.target.id == user.id: await nuke_check(guild, entry.user.id, "ban"); break
    except: pass

@bot.event
async def on_guild_channel_delete(channel):
    try:
        await asyncio.sleep(0.5)
        async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
            await nuke_check(channel.guild, entry.user.id, "ch_del"); break
    except: pass

@bot.event
async def on_guild_role_delete(role):
    try:
        await asyncio.sleep(0.5)
        async for entry in role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_delete):
            await nuke_check(role.guild, entry.user.id, "role_del"); break
    except: pass

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot: return
    if message.guild: await check_spam(message)
    await bot.process_commands(message)

# ══════════════════════════════════════════════
#  COMMANDES
# ══════════════════════════════════════════════

@bot.tree.command(name="aide", description="Commandes AEGIS Security")
async def aide(i: discord.Interaction):
    e = discord.Embed(title="🛡️  AEGIS SECURITY — Commandes", color=C.CYAN, timestamp=datetime.now(timezone.utc))
    e.add_field(name="⛔  Modération", value="`/ban` `/unban` `/kick` `/mute` `/unmute` `/warn` `/unwarn` `/warns` `/rename` `/purge`", inline=False)
    e.add_field(name="🔒  Salons",     value="`/lock` `/unlock` `/slowmode`", inline=False)
    e.add_field(name="🛡️  Protection", value="`/antiraid` `/antispam` `/antinuke` `/setlogs`", inline=False)
    e.set_footer(text="AEGIS SECURITY  ◈  discord.gg/6rN8pneGdy")
    await i.response.send_message(embed=e)

@bot.tree.command(name="warn", description="Avertir un membre")
@app_commands.describe(membre="Le membre", raison="Raison")
@app_commands.default_permissions(moderate_members=True)
async def warn(i: discord.Interaction, membre: discord.Member, raison: str="Aucune raison"):
    if not can_target(i.user, membre):
        return await i.response.send_message(embed=er("Impossible","Tu ne peux pas agir sur ce membre."), ephemeral=True)
    gid, uid = str(i.guild.id), str(membre.id)
    bot.warnings.setdefault(gid, {}).setdefault(uid, []).append(
        {"r": raison, "by": str(i.user.id), "at": datetime.now(timezone.utc).isoformat()})
    count = len(bot.warnings[gid][uid])
    e = emb(f"⚠️  Avertissement", f"**Membre :** {membre.mention}\n**Raison :** {raison}\n**Total :** {count}", C.ORANGE)
    sanction = None
    if count == 3:
        try: await membre.timeout(datetime.now(timezone.utc)+timedelta(hours=1), reason="3 warns"); sanction="Mute 1h"
        except: pass
    elif count == 5:
        try: await membre.timeout(datetime.now(timezone.utc)+timedelta(hours=24), reason="5 warns"); sanction="Mute 24h"
        except: pass
    elif count >= 7:
        try: await membre.kick(reason="7 warns"); sanction="Kick"
        except: pass
    if sanction: e.add_field(name="⚡ Sanction auto", value=sanction)
    await i.response.send_message(embed=e)
    await log(i.guild, "Warn", f"**Membre :** {membre}\n**Raison :** {raison}\n**Par :** {i.user}", C.ORANGE)
    try: await membre.send(embed=emb(f"⚠️  Avertissement", f"**Serveur :** {i.guild.name}\n**Raison :** {raison}\n**Total :** {count}", C.ORANGE))
    except: pass

@bot.tree.command(name="unwarn", description="Retirer un avertissement")
@app_commands.describe(membre="Le membre")
@app_commands.default_permissions(moderate_members=True)
async def unwarn(i: discord.Interaction, membre: discord.Member):
    lst = bot.warnings.get(str(i.guild.id), {}).get(str(membre.id), [])
    if not lst: return await i.response.send_message(embed=inf("Aucun warn", f"{membre.mention} est clean."), ephemeral=True)
    lst.pop()
    await i.response.send_message(embed=ok("Warn retiré", f"{membre.mention} → **{len(lst)}** warn(s)"))

@bot.tree.command(name="warns", description="Voir les avertissements")
@app_commands.describe(membre="Le membre")
@app_commands.default_permissions(moderate_members=True)
async def warns(i: discord.Interaction, membre: Optional[discord.Member]=None):
    m = membre or i.user
    lst = bot.warnings.get(str(i.guild.id), {}).get(str(m.id), [])
    if not lst: return await i.response.send_message(embed=inf("Aucun warn", f"{m.mention} est clean ✅"), ephemeral=True)
    e = emb(f"⚠️  Warns de {m.display_name}", f"**Total :** {len(lst)}", C.ORANGE)
    for idx, w in enumerate(lst[-10:], 1):
        e.add_field(name=f"#{idx}", value=f"**Raison :** {w['r']}\n**Date :** {w['at'][:10]}", inline=True)
    await i.response.send_message(embed=e)

@bot.tree.command(name="ban", description="Bannir un membre")
@app_commands.describe(membre="Le membre", raison="Raison")
@app_commands.default_permissions(ban_members=True)
async def ban(i: discord.Interaction, membre: discord.Member, raison: str="Aucune"):
    if not can_target(i.user, membre):
        return await i.response.send_message(embed=er("Impossible","Tu ne peux pas bannir ce membre."), ephemeral=True)
    try:
        await membre.ban(reason=raison)
        await i.response.send_message(embed=emb(f"⛔  Banni", f"{membre.mention}\n**Raison :** {raison}", C.RED))
        await log(i.guild, "Ban", f"**Membre :** {membre}\n**Raison :** {raison}\n**Par :** {i.user}", C.RED)
    except discord.Forbidden:
        await i.response.send_message(embed=er("Permission manquante","Mon rôle doit être plus haut."), ephemeral=True)

@bot.tree.command(name="unban", description="Débannir un utilisateur")
@app_commands.describe(user_id="ID de l'utilisateur")
@app_commands.default_permissions(ban_members=True)
async def unban(i: discord.Interaction, user_id: str):
    try:
        user = await bot.fetch_user(int(user_id))
        await i.guild.unban(user)
        await i.response.send_message(embed=ok("Débanni", str(user)))
    except:
        await i.response.send_message(embed=er("Introuvable","Vérifie l'ID."), ephemeral=True)

@bot.tree.command(name="kick", description="Expulser un membre")
@app_commands.describe(membre="Le membre", raison="Raison")
@app_commands.default_permissions(kick_members=True)
async def kick(i: discord.Interaction, membre: discord.Member, raison: str="Aucune"):
    if not can_target(i.user, membre):
        return await i.response.send_message(embed=er("Impossible","Tu ne peux pas kick ce membre."), ephemeral=True)
    try:
        await membre.kick(reason=raison)
        await i.response.send_message(embed=emb(f"⚡  Expulsé", f"{membre.mention}\n**Raison :** {raison}", C.ORANGE))
        await log(i.guild, "Kick", f"**Membre :** {membre}\n**Raison :** {raison}\n**Par :** {i.user}", C.ORANGE)
    except discord.Forbidden:
        await i.response.send_message(embed=er("Permission manquante","Mon rôle doit être plus haut."), ephemeral=True)

@bot.tree.command(name="mute", description="Mute un membre")
@app_commands.describe(membre="Le membre", duree="Durée en minutes")
@app_commands.default_permissions(moderate_members=True)
async def mute(i: discord.Interaction, membre: discord.Member, duree: int=10):
    if not can_target(i.user, membre):
        return await i.response.send_message(embed=er("Impossible","Tu ne peux pas mute ce membre."), ephemeral=True)
    try:
        await membre.timeout(datetime.now(timezone.utc)+timedelta(minutes=duree))
        await i.response.send_message(embed=emb(f"🔇  Muté", f"{membre.mention} — **{duree} min**", C.BLUE))
    except discord.Forbidden:
        await i.response.send_message(embed=er("Permission manquante"), ephemeral=True)

@bot.tree.command(name="unmute", description="Unmute un membre")
@app_commands.describe(membre="Le membre")
@app_commands.default_permissions(moderate_members=True)
async def unmute(i: discord.Interaction, membre: discord.Member):
    await membre.timeout(None)
    await i.response.send_message(embed=ok("Unmute", f"{membre.mention}"))

@bot.tree.command(name="rename", description="Renommer un membre")
@app_commands.describe(membre="Le membre", pseudo="Nouveau pseudo")
@app_commands.default_permissions(manage_nicknames=True)
async def rename(i: discord.Interaction, membre: discord.Member, pseudo: str):
    old = membre.display_name
    try:
        await membre.edit(nick=pseudo)
        await i.response.send_message(embed=ok("Renommé", f"`{old}` → `{pseudo}`"))
    except discord.Forbidden:
        await i.response.send_message(embed=er("Permission manquante"), ephemeral=True)

@bot.tree.command(name="purge", description="Supprimer des messages")
@app_commands.describe(nombre="Nombre (max 100)")
@app_commands.default_permissions(manage_messages=True)
async def purge(i: discord.Interaction, nombre: int):
    await i.response.defer(ephemeral=True)
    deleted = await i.channel.purge(limit=min(nombre, 100))
    await i.followup.send(embed=ok("Purge", f"**{len(deleted)}** messages supprimés."))

@bot.tree.command(name="lock", description="Verrouiller un salon")
@app_commands.describe(salon="Salon (vide = actuel)")
@app_commands.default_permissions(manage_channels=True)
async def lock(i: discord.Interaction, salon: Optional[discord.TextChannel]=None):
    target = salon or i.channel
    await i.response.defer(ephemeral=True)
    try:
        ow = target.overwrites_for(i.guild.default_role)
        ow.update(send_messages=False)
        await target.set_permissions(i.guild.default_role, overwrite=ow)
        await i.followup.send(embed=emb("🔒  Verrouillé", target.mention, C.RED))
    except discord.Forbidden:
        await i.followup.send(embed=er("Permission manquante"))

@bot.tree.command(name="unlock", description="Déverrouiller un salon")
@app_commands.describe(salon="Salon (vide = actuel)")
@app_commands.default_permissions(manage_channels=True)
async def unlock(i: discord.Interaction, salon: Optional[discord.TextChannel]=None):
    target = salon or i.channel
    await i.response.defer(ephemeral=True)
    try:
        ow = target.overwrites_for(i.guild.default_role)
        ow.update(send_messages=True, view_channel=True)
        await target.set_permissions(i.guild.default_role, overwrite=ow)
        await i.followup.send(embed=ok("🔓  Déverrouillé", target.mention))
    except discord.Forbidden:
        await i.followup.send(embed=er("Permission manquante"))

@bot.tree.command(name="slowmode", description="Mode lent sur un salon")
@app_commands.describe(secondes="Délai (0 = désactiver)", salon="Salon (vide = actuel)")
@app_commands.default_permissions(manage_channels=True)
async def slowmode(i: discord.Interaction, secondes: int, salon: Optional[discord.TextChannel]=None):
    target = salon or i.channel
    await i.response.defer(ephemeral=True)
    try:
        await target.edit(slowmode_delay=secondes)
        label = f"{secondes}s" if secondes > 0 else "Désactivé"
        await i.followup.send(embed=ok(f"Slowmode — {label}", f"Sur {target.mention}"))
    except discord.Forbidden:
        await i.followup.send(embed=er("Permission manquante"))

@bot.tree.command(name="setlogs", description="Configurer le salon de logs")
@app_commands.describe(salon="Salon des logs")
@app_commands.default_permissions(administrator=True)
async def setlogs(i: discord.Interaction, salon: discord.TextChannel):
    bot.logs_ch[str(i.guild.id)] = salon.id
    await i.response.send_message(embed=ok("Logs configurés", f"Dans {salon.mention}"))

@bot.tree.command(name="antiraid", description="Configurer l'anti-raid")
@app_commands.describe(activer="Activer", seuil="Joins par 10s", action="kick ou ban")
@app_commands.default_permissions(administrator=True)
async def antiraid(i: discord.Interaction, activer: bool=True, seuil: int=5, action: str="kick"):
    bot.raid_cfg[str(i.guild.id)] = {"enabled": activer, "threshold": seuil, "action": action}
    await i.response.send_message(embed=emb("◈  Anti-Raid",
        f"**Statut :** {'✅' if activer else '❌'}\n**Seuil :** {seuil}/10s\n**Action :** {action}", C.PINK))

@bot.tree.command(name="antispam", description="Configurer l'anti-spam")
@app_commands.describe(activer="Activer", messages="Max messages", fenetre="Secondes",
                        mentions="Max mentions", action="mute/kick/ban", duree_mute="Minutes mute")
@app_commands.default_permissions(administrator=True)
async def antispam(i: discord.Interaction, activer: bool=True, messages: int=5,
                   fenetre: int=5, mentions: int=5, action: str="mute", duree_mute: int=5):
    bot.spam_cfg[str(i.guild.id)] = {"enabled": activer, "limit": messages, "window": fenetre,
                                      "mentions": mentions, "action": action, "dur": duree_mute}
    await i.response.send_message(embed=emb("◈  Anti-Spam",
        f"**Statut :** {'✅' if activer else '❌'}\n**Messages :** {messages}/{fenetre}s\n**Action :** {action}", C.PINK))

@bot.tree.command(name="antinuke", description="Configurer l'anti-nuke")
@app_commands.describe(activer="Activer", seuil="Actions max/10s", action="kick ou ban",
                        whitelist_add="ID à whitelister", whitelist_rem="ID à retirer")
@app_commands.default_permissions(administrator=True)
async def antinuke(i: discord.Interaction, activer: bool=True, seuil: int=5, action: str="kick",
                   whitelist_add: Optional[str]=None, whitelist_rem: Optional[str]=None):
    gid = str(i.guild.id)
    cfg = bot.nuke_cfg.setdefault(gid, default_nuke())
    cfg.update({"enabled": activer, "threshold": max(1, seuil), "action": action if action in ("kick","ban") else "kick"})
    wl = cfg["whitelist"]
    if whitelist_add:
        try:
            uid = int(whitelist_add)
            if uid not in wl: wl.append(uid)
        except: pass
    if whitelist_rem:
        try:
            uid = int(whitelist_rem)
            if uid in wl: wl.remove(uid)
        except: pass
    wl_txt = ", ".join([f"<@{uid}>" for uid in wl]) or "Aucun"
    await i.response.send_message(embed=emb("☢️  Anti-Nuke",
        f"**Statut :** {'✅' if activer else '❌'}\n**Seuil :** {seuil}/10s\n"
        f"**Sanction :** {cfg['action']}\n**Whitelist :** {wl_txt}\n\n"
        f"**Surveille :** bans • suppressions salons • suppressions rôles", C.RED))

# ── Run ──
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    token = os.environ.get('DISCORD_BOT_TOKEN_SECURITY')
    if token:
        logger.info("🛡️ AEGIS SECURITY démarre...")
        bot.run(token)
    else:
        logger.error("❌ DISCORD_BOT_TOKEN_SECURITY manquant !")
