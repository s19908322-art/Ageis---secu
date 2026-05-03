"""
╔══════════════════════════════════════════════╗
║         AEGIS AI — Bot Discord               ║
║   IA au centre • Components V2               ║
╚══════════════════════════════════════════════╝
Variables Railway :
  DISCORD_BOT_TOKEN  → token du bot
  GROQ_API_KEY       → clé API groq (gsk_...)
  BOT_OWNER_ID       → ton ID Discord (optionnel)

Requirements:
  discord.py[voice]>=2.6.0
  python-dotenv>=1.0.0
  PyNaCl>=1.5.0
  yt-dlp>=2024.1.1
  aiohttp>=3.9.0
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import os, logging, asyncio, random, re, aiohttp, json
from datetime import datetime, timezone, timedelta
from typing import Optional
from collections import defaultdict, deque


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('AegisAI')

BOT_OWNER_ID = int(os.environ.get('BOT_OWNER_ID', '0'))

# ══════════════════════════════════════════════
#  PERSISTANCE JSON  (Railway Volume conseillé)
#  Configure DATA_PATH=/data/aegis.json sur Railway
#  + monte un Volume sur /data pour que ça survive aux redeploys
# ══════════════════════════════════════════════
DATA_PATH = os.environ.get('DATA_PATH', '/data/aegis.json')
if not os.path.isdir(os.path.dirname(DATA_PATH)):
    DATA_PATH = './aegis_data.json'  # fallback local

PERSIST_KEYS = [
    'giveaways', 'polls', 'warnings', 'xp_data', 'arrivee', 'depart_ch',
    'auto_roles', 'verif_roles', 'logs_ch', 'ticket_cfg', 'temp_voices',
    'raid_cfg', 'spam_cfg', 'nuke_cfg', 'backups', 'verif_quiz',
    'logs_filters', 'tempbans', 'mod_history', 'nuke_paused_until', 'rolemenu_cfg',
]

def _load_data() -> dict:
    try:
        with open(DATA_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            logger.info(f"💾 Données chargées depuis {DATA_PATH}")
            return data
    except FileNotFoundError:
        logger.info(f"💾 Pas de fichier {DATA_PATH}, démarrage vierge")
        return {}
    except Exception as e:
        logger.error(f"💾 Erreur chargement: {e}")
        return {}

def _save_data():
    try:
        snapshot = {k: getattr(bot, k, {}) for k in PERSIST_KEYS}
        os.makedirs(os.path.dirname(DATA_PATH) or '.', exist_ok=True)
        tmp = DATA_PATH + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(snapshot, f, default=str, ensure_ascii=False)
        os.replace(tmp, DATA_PATH)
    except Exception as e:
        logger.error(f"💾 Erreur sauvegarde: {e}")

# ══════════════════════════════════════════════
#  THÈME NÉON
# ══════════════════════════════════════════════
class C:
    # Palette signature Aegis (rose néon sur bleu royal)
    AEGIS_PINK    = 0xE57BFF   # Rose néon (logo)
    AEGIS_MAGENTA = 0xFF4FD8   # Magenta vif
    AEGIS_BLUE    = 0x2B3FD9   # Bleu royal (fond logo)
    AEGIS_INDIGO  = 0x3949E0   # Indigo clair
    AEGIS_WHITE   = 0xF5E6FF   # Blanc rosé

    # Alias conservés pour compatibilité (rebrandés)
    NEON_PINK   = AEGIS_PINK
    NEON_CYAN   = AEGIS_MAGENTA   # accent principal = rose Aegis
    NEON_BLUE   = AEGIS_BLUE
    NEON_GOLD   = AEGIS_PINK      # highlights "gold" → rose
    NEON_GREEN  = 0x7CFFB0
    NEON_ORANGE = 0xFF9F6B
    NEON_RED    = 0xFF3D7F
    DARK        = 0x0D0D0D
    OK    = NEON_GREEN
    ERR   = NEON_RED
    INFO  = AEGIS_PINK
    WARN  = NEON_ORANGE
    MOD   = AEGIS_MAGENTA
    SYS   = AEGIS_BLUE

LINE = "─────────────────────"

# ══════════════════════════════════════════════
#  HELPERS EMBED CLASSIQUE (pour ephemeral etc.)
# ══════════════════════════════════════════════
def emb(title: str, desc: str=None, color: int=C.NEON_CYAN, footer: str=None) -> discord.Embed:
    e = discord.Embed(title=title, description=desc, color=color,
                      timestamp=datetime.now(timezone.utc))
    e.set_footer(text=footer or "AEGIS AI  ◈  discord.gg/6rN8pneGdy")
    return e

def ok(t, d=None):      return emb(f"✅  {t}", d, C.NEON_GREEN)
def er(t, d=None):      return emb(f"❌  {t}", d, C.NEON_RED)
def inf(t, d=None):     return emb(f"◈  {t}", d, C.NEON_CYAN)
def warn(t, d=None):    return emb(f"⚠️  {t}", d, C.NEON_ORANGE)

# ══════════════════════════════════════════════
#  COMPONENTS V2 — LAYOUTS VITRINES
# ══════════════════════════════════════════════

class AIChatLayout(discord.ui.LayoutView):
    """Layout V2 pour /ai chat — Section avec thumbnail avatar"""
    def __init__(self, question: str, reponse: str, user: discord.Member):
        super().__init__()
        ts = f"<t:{int(datetime.now(timezone.utc).timestamp())}:R>"
        container = discord.ui.Container(
            discord.ui.Section(
                discord.ui.TextDisplay(f"## ◉  AEGIS AI"),
                discord.ui.TextDisplay(reponse),
                accessory=discord.ui.Thumbnail(user.display_avatar.url)
            ),
            discord.ui.Separator(spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(
                f"-# 💬 {user.display_name} — {ts}  ◈  discord.gg/6rN8pneGdy"
            ),
            accent_color=C.NEON_PINK
        )
        self.add_item(container)


class RankLayout(discord.ui.LayoutView):
    """Layout V2 pour /stats rank"""
    def __init__(self, member: discord.Member, level: int, xp: int, req: int,
                 rank: int, messages: int):
        super().__init__()
        pct  = int(xp / req * 100) if req > 0 else 0
        full = pct // 10
        bar  = "█" * full + "░" * (10 - full)
        container = discord.ui.Container(
            discord.ui.Section(
                discord.ui.TextDisplay(f"## ◆  {member.display_name}"),
                discord.ui.TextDisplay(
                    f"**Niveau** `{level}`  ·  **Classement** `#{rank}`\n"
                    f"**XP** `{xp}` / `{req}`  ·  **Messages** `{messages}`\n\n"
                    f"`{bar}` **{pct}%**"
                ),
                accessory=discord.ui.Thumbnail(member.display_avatar.url)
            ),
            accent_color=C.NEON_GOLD
        )
        self.add_item(container)


class UserInfoLayout(discord.ui.LayoutView):
    """Layout V2 pour /stats userinfo"""
    def __init__(self, member: discord.Member, level: int, xp: int):
        super().__init__()
        roles = [r.mention for r in member.roles if r.name != "@everyone"]
        joined = member.joined_at.strftime("%d/%m/%Y") if member.joined_at else "?"
        created = member.created_at.strftime("%d/%m/%Y")
        container = discord.ui.Container(
            discord.ui.Section(
                discord.ui.TextDisplay(f"## ◈  {member.display_name}"),
                discord.ui.TextDisplay(
                    f"**Discord** `{member}`\n"
                    f"**ID** `{member.id}`\n"
                    f"**Créé le** `{created}`  ·  **Rejoint le** `{joined}`\n"
                    f"**Niveau** `{level}` ({xp} XP)  ·  **Bot** {'✅' if member.bot else '❌'}"
                ),
                accessory=discord.ui.Thumbnail(member.display_avatar.url)
            ),
            discord.ui.Separator(spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(
                f"**◉ Rôles ({len(roles)})**\n" + (" ".join(roles[:10]) if roles else "Aucun")
            ),
            discord.ui.Separator(spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(f"-# AEGIS AI  ◈  discord.gg/6rN8pneGdy"),
            accent_color=C.NEON_CYAN
        )
        self.add_item(container)


class TopLayout(discord.ui.LayoutView):
    """Layout V2 pour /stats top"""
    def __init__(self, entries: list):
        super().__init__()
        medals = ["🥇","🥈","🥉"] + [f"`#{i}`" for i in range(4, 11)]
        lines  = "\n".join(
            f"{medals[idx]}  **{name}** — Niveau `{lv}` ({xp} XP)"
            for idx, (name, lv, xp) in enumerate(entries)
        )
        container = discord.ui.Container(
            discord.ui.TextDisplay(f"## ◆  Top 10 XP"),
            discord.ui.Separator(spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(lines or "*Aucun joueur pour l'instant.*"),
            discord.ui.Separator(spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(f"-# AEGIS AI  ◈  discord.gg/6rN8pneGdy"),
            accent_color=C.NEON_GOLD
        )
        self.add_item(container)


class ServerInfoLayout(discord.ui.LayoutView):
    """Layout V2 pour /stats serverinfo"""
    def __init__(self, guild: discord.Guild, humans: int, bots: int):
        super().__init__()
        icon_url = guild.icon.url if guild.icon else None
        owner    = guild.owner.mention if guild.owner else "?"
        created  = guild.created_at.strftime("%d/%m/%Y")
        section_content = (
            f"## ◈  {guild.name}\n"
            f"**ID** `{guild.id}`\n"
            f"**Propriétaire** {owner}  ·  **Créé le** `{created}`\n"
            f"**Membres** `{humans}` humains / `{bots}` bots\n"
            f"**Salons** `{len(guild.text_channels)}` texte / `{len(guild.voice_channels)}` vocal\n"
            f"**Rôles** `{len(guild.roles)}`  ·  **Boosts** `{guild.premium_subscription_count}` (Niv. {guild.premium_tier})"
        )
        if icon_url:
            section = discord.ui.Section(
                discord.ui.TextDisplay(section_content),
                accessory=discord.ui.Thumbnail(icon_url)
            )
        else:
            section = discord.ui.Section(discord.ui.TextDisplay(section_content))

        container = discord.ui.Container(
            section,
            discord.ui.Separator(spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(f"-# AEGIS AI  ◈  discord.gg/6rN8pneGdy"),
            accent_color=C.NEON_CYAN
        )
        self.add_item(container)


class AideLayout(discord.ui.LayoutView):
    """Layout V2 pour /aide"""
    def __init__(self):
        super().__init__()
        container = discord.ui.Container(
            discord.ui.TextDisplay(
                "# ◈  AEGIS AI\n"
                "Bot Discord intelligent qui **anime ton serveur** grâce à l'IA.\n"
                "Il répond, relance les discussions et rend ton serveur actif."
            ),
            discord.ui.Separator(),
            discord.ui.TextDisplay(
                "## ◉  /ai\n"
                "`chat` · `relance` · `mode` · `memory` · `question` · `resume`\n\n"
                "## ⛔  /mod\n"
                "`ban` · `unban` · `kick` · `mute` · `unmute` · `tempban` · `warn` · `unwarn` · `warns` · `historique` · `purge` · `rename` · `lock` · `unlock` · `slowmode`\n\n"
                "## ♪  /music\n"
                "`play` · `pause` · `resume` · `skip` · `stop` · `queue` · `nowplaying` · `volume` · `lyrics`"
            ),
            discord.ui.Separator(spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(
                "## ▶  /fun\n"
                "`tirage` · `sondage_rapide` · `avatar` · `dire` · `embed` · `dmall` · `ia_image`\n\n"
                "## ◆  /stats\n"
                "`rank` · `top` · `userinfo` · `serverinfo`\n\n"
                "## ⚙️  /server\n"
                "`setup` · `arrivee` · `depart` · `panel` · `reglement` · `verification` · `verification_quiz` · `backup` · `restore` · `autorole` · `rolemenu` · `tempvoice` · `antiraid` · `antispam` · `antinuke` · `antinuke_pause` · `logs_filter` · `suggestion` · `creersalon` · `creervoice` · `supprimersalon` · `creerole` · `addrole` · `removerole` · `roleall`\n\n"
                "## 🎉  /events\n"
                "`giveaway` · `reroll` · `poll` · `bingo` · `bingo_stop` · `trivia`"
            ),
            discord.ui.Separator(spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(
                "## ◉  IA directe\n"
                "Écris **aegis** dans un message ou mentionne **@AEGIS AI**\n\n"
                "## ☢️  Owner\n"
                "`/admin_panel` · `/owner_dmall_ultime`"
            ),
            discord.ui.Separator(spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(f"-# AEGIS AI  ◈  discord.gg/6rN8pneGdy"),
            accent_color=C.NEON_CYAN
        )
        self.add_item(container)


class WelcomeLayout(discord.ui.LayoutView):
    """Layout V2 pour message de bienvenue"""
    def __init__(self, member: discord.Member, count: int):
        super().__init__()
        created = member.created_at.strftime("%d/%m/%Y")
        container = discord.ui.Container(
            discord.ui.Section(
                discord.ui.TextDisplay(
                    f"## ◈  Bienvenue sur {member.guild.name} !\n"
                    f"**{member.mention}** vient de rejoindre le serveur.\n\n"
                    f"**Compte créé le** `{created}`\n"
                    f"**Membre numéro** `#{count}`"
                ),
                accessory=discord.ui.Thumbnail(member.display_avatar.url)
            ),
            discord.ui.Separator(spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(f"-# {member.guild.name}  ◈  {count} membres"),
            accent_color=C.NEON_CYAN
        )
        self.add_item(container)


class GuildJoinLayout(discord.ui.LayoutView):
    """Layout V2 pour message d'arrivée du bot"""
    def __init__(self, bot_user):
        super().__init__()
        container = discord.ui.Container(
            discord.ui.TextDisplay(
                "# ◈  AEGIS AI — En ligne\n"
                "Salut. Je suis **AEGIS AI**, ton assistant Discord intelligent.\n"
                f"{LINE}"
            ),
            discord.ui.Separator(spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(
                "## Ce que je fais vraiment\n"
                "▸ **J'anime ton serveur** — je relance les discussions mortes\n"
                "▸ **Je réponds** — écris `aegis` ou mentionne-moi\n"
                "▸ **Je retiens le contexte** — je me souviens de la conversation\n"
                f"{LINE}"
            ),
            discord.ui.Separator(spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(
                "## Et en plus\n"
                "▸ **Modération** — `/mod ban` `/mod kick` `/mod mute`...\n"
                "▸ **Musique** — `/music play`\n"
                "▸ **Systèmes** — tickets, vérification, giveaway, sondages\n"
                "▸ **XP & Stats** — niveaux, classement, profils\n"
                f"{LINE}"
            ),
            discord.ui.Separator(spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(
                "## ☢️ Protections activées automatiquement\n"
                "▸ Anti-raid  ▸ Anti-spam  ▸ Anti-nuke\n\n"
                "Pour tout voir : `/aide`\n"
                "*Le protocole est en ligne. Bonne chance.*"
            ),
            discord.ui.Separator(spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(f"-# AEGIS AI  ◈  discord.gg/6rN8pneGdy"),
            accent_color=C.NEON_CYAN
        )
        self.add_item(container)


class QuestionLayout(discord.ui.LayoutView):
    """Layout V2 pour /ai question"""
    def __init__(self, question: str):
        super().__init__()
        container = discord.ui.Container(
            discord.ui.TextDisplay(f"## ◉  Question du jour"),
            discord.ui.Separator(spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(question),
            discord.ui.Separator(spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(f"-# Posée par AEGIS AI  ◈  discord.gg/6rN8pneGdy"),
            accent_color=C.NEON_PINK
        )
        self.add_item(container)


class MusicLayout(discord.ui.LayoutView):
    """Layout V2 pour /music play (now playing)"""
    def __init__(self, track: dict, status: str = "▶ Lecture"):
        super().__init__()
        duration = fmt(track.get("duration", 0))
        thumb    = track.get("thumb", "")
        webpage  = track.get("webpage", "")
        title    = track.get("title", "?")

        content = (
            f"## ♪  {status}\n"
            f"**{title}**\n"
            f"⏱️ `{duration}`"
        )
        if webpage:
            content += f"\n[▶ Ouvrir sur YouTube]({webpage})"

        if thumb:
            section = discord.ui.Section(
                discord.ui.TextDisplay(content),
                accessory=discord.ui.Thumbnail(thumb)
            )
        else:
            section = discord.ui.Section(discord.ui.TextDisplay(content))

        container = discord.ui.Container(
            section,
            discord.ui.Separator(spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(f"-# AEGIS AI  ◈  discord.gg/6rN8pneGdy"),
            accent_color=C.NEON_CYAN
        )
        self.add_item(container)


class ModActionLayout(discord.ui.LayoutView):
    """Layout V2 pour les actions de modération (ban/kick/mute/warn)"""
    def __init__(self, emoji: str, titre: str, membre: discord.Member,
                 raison: str, extra: str = None, color: int = C.NEON_RED):
        super().__init__()
        content = (
            f"## {emoji}  {titre}\n"
            f"**Membre** {membre.mention} (`{membre}`)\n"
            f"**Raison** {raison}"
        )
        if extra:
            content += f"\n{extra}"

        container = discord.ui.Container(
            discord.ui.Section(
                discord.ui.TextDisplay(content),
                accessory=discord.ui.Thumbnail(membre.display_avatar.url)
            ),
            discord.ui.Separator(spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(f"-# AEGIS AI  ◈  discord.gg/6rN8pneGdy"),
            accent_color=color
        )
        self.add_item(container)


class LevelUpLayout(discord.ui.LayoutView):
    """Layout V2 pour level up XP"""
    def __init__(self, member: discord.Member, level: int, next_req: int = 0):
        super().__init__()
        next_line = f"\n*Prochain palier :* `{next_req} XP`" if next_req else ""
        container = discord.ui.Container(
            discord.ui.Section(
                discord.ui.TextDisplay(
                    f"## ◆  Level Up !\n"
                    f"{member.mention} atteint le **niveau {level}** ◆{next_line}"
                ),
                accessory=discord.ui.Thumbnail(member.display_avatar.url)
            ),
            accent_color=C.NEON_GOLD
        )
        self.add_item(container)


class AvatarLayout(discord.ui.LayoutView):
    """Layout V2 pour /fun avatar"""
    def __init__(self, member: discord.Member):
        super().__init__()
        container = discord.ui.Container(
            discord.ui.TextDisplay(f"## ◈  Avatar de {member.display_name}"),
            discord.ui.MediaGallery(
                discord.MediaGalleryItem(
                    media=member.display_avatar.with_size(1024).url,
                    description=f"Avatar de {member.display_name}"
                )
            ),
            discord.ui.Separator(spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(f"-# ID : {member.id}  ◈  AEGIS AI"),
            accent_color=C.NEON_CYAN
        )
        self.add_item(container)


# ══════════════════════════════════════════════
#  BOT
# ══════════════════════════════════════════════
intents = discord.Intents.all()

class Aegis(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!_', intents=intents, help_command=None)
        self.giveaways   = {}
        self.polls       = {}
        self.warnings    = {}
        self.xp_data     = {}
        self.xp_cd       = {}
        self.ai_cd       = {}
        self.vc_pool     = {}
        self.queues      = {}
        self.now_playing = {}
        self.msg_cache   = defaultdict(list)
        self.arrivee     = {}
        self.depart_ch   = {}
        self.auto_roles  = {}
        self.verif_roles = {}
        self.logs_ch     = {}
        self.ticket_cfg  = {}
        self.temp_voices = {}
        self.raid_cfg    = {}
        self.raid_cache  = {}
        self.spam_cfg    = {}
        self.nuke_cfg    = {}
        self.nuke_track  = {}
        self.backups     = {}
        self.verif_quiz  = {}
        self.rolemenu_cfg = {}
        self._join_cache   = {}
        self._remove_cache = {}
        self.ai_memory: dict[str, deque] = defaultdict(lambda: deque(maxlen=50))
        self.ai_active: dict[str, bool] = {}
        # Nouveautés
        self.logs_filters: dict = {}      # {gid: ["ban","kick",...]}
        self.tempbans: dict    = {}        # {gid: {uid: iso_unban_time}}
        self.mod_history: dict = {}        # {gid: {uid: [{type,by,reason,at}]}}
        self.nuke_paused_until: dict = {}  # {gid: iso}
        self.ai_guild_cd: dict = {}        # cooldown IA par guild
        self.trivia_active: dict = {}      # {cid: {answer, end}}
        self.bingo_active: dict = {}       # {cid: {numbers, drawn}}

    async def setup_hook(self):
        # Load données persistantes
        data = _load_data()
        for k in PERSIST_KEYS:
            if k in data and isinstance(data[k], dict):
                setattr(self, k, data[k])
        for v in [TicketView(), CloseView(), VerifyView(), RulesView(), ApplyView()]:
            self.add_view(v)
        # Restaurer les vues persistantes des giveaways/polls actifs
        for mid, g in list(self.giveaways.items()):
            if not g.get("ended"):
                try: self.add_view(GAView(mid))
                except Exception as e: logger.error(f"restore GA {mid}: {e}")
        for mid, p in list(self.polls.items()):
            if not p.get("ended"):
                try: self.add_view(PollView(mid, p.get("opts", [])))
                except Exception as e: logger.error(f"restore poll {mid}: {e}")
        # Restaurer les vues VerifQuiz persistantes
        for gid, cfg in self.verif_quiz.items():
            if cfg.get("true_code") and cfg.get("role_id"):
                try: self.add_view(VerifQuizView(gid))
                except Exception as e: logger.error(f"restore verifquiz {gid}: {e}")
        # Restaurer les vues RoleMenu persistantes
        for gid, role_ids in self.rolemenu_cfg.items():
            try:
                guild = self.get_guild(int(gid))
                if guild:
                    roles = [guild.get_role(int(rid)) for rid in role_ids]
                    roles = [r for r in roles if r]
                    if roles:
                        self.add_view(RoleMenuView(roles, int(gid)))
            except Exception as e: logger.error(f"restore rolemenu {gid}: {e}")
        try:
            n = await self.tree.sync()
            logger.info(f"✅ {len(n)} commandes sync")
        except Exception as e:
            logger.error(f"Sync: {e}")

bot = Aegis()

# ══════════════════════════════════════════════
#  ERROR HANDLER
# ══════════════════════════════════════════════
@bot.tree.error
async def on_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        e = er("Permission refusée", "Tu n'as pas la permission nécessaire.")
    elif isinstance(error, app_commands.BotMissingPermissions):
        e = er("Permission manquante (bot)", f"`{str(error)[:100]}`")
    else:
        logger.error(f"[{getattr(interaction.command,'name','?')}] {error}")
        e = er("Erreur", f"`{str(error)[:200]}`")
    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=e, ephemeral=True)
        else:
            await interaction.response.send_message(embed=e, ephemeral=True)
    except Exception:
        pass

# ══════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════
def xp_req(lv): return 100*(lv**2) + 50*lv

def get_xp(gid, uid):
    return bot.xp_data.setdefault(gid, {}).setdefault(uid, {"xp":0,"level":0,"messages":0})

def fmt(s):
    if not s: return "?"
    m, s = divmod(int(s), 60); h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

def can_target(actor: discord.Member, target: discord.Member) -> bool:
    if not actor or not target: return False
    if target.id == actor.guild.owner_id: return False
    if target.id == actor.guild.me.id: return False
    ar = getattr(actor, 'top_role', None)
    tr = getattr(target, 'top_role', None)
    if ar is None or tr is None: return True
    return ar > tr

async def log(guild, title, desc, color=C.NEON_CYAN):
    gid = str(guild.id)
    if gid in bot.logs_ch:
        ch = guild.get_channel(bot.logs_ch[gid])
        if ch:
            try: await ch.send(embed=emb(f"◈  {title}", desc, color))
            except: pass

def check_perms(channel, guild_me) -> bool:
    perms = channel.permissions_for(guild_me)
    return perms.view_channel and perms.send_messages and perms.embed_links

def default_raid_cfg():  return {"enabled": True,  "threshold": 5,  "action": "kick"}
def default_spam_cfg():  return {"enabled": True,  "limit": 5, "window": 5, "mentions": 5, "action": "mute", "dur": 5}
def default_nuke_cfg():  return {"enabled": True,  "threshold": 5,  "action": "kick", "whitelist": []}

def add_history(guild_id: str, user_id: str, action: str, by: str, reason: str):
    """Ajoute une entrée dans l'historique de modération"""
    bot.mod_history.setdefault(guild_id, {}).setdefault(user_id, []).append({
        "type": action, "by": str(by), "reason": str(reason)[:300],
        "at": datetime.now(timezone.utc).isoformat()
    })
    # garde max 50 entrées par user
    bot.mod_history[guild_id][user_id] = bot.mod_history[guild_id][user_id][-50:]

# ══════════════════════════════════════════════
#  TÂCHES PÉRIODIQUES (save + tempbans)
# ══════════════════════════════════════════════
@tasks.loop(minutes=2)
async def save_loop():
    _save_data()

@tasks.loop(minutes=1)
async def tempban_loop():
    """Auto-déban des tempbans expirés"""
    now = datetime.now(timezone.utc)
    for gid, users in list(bot.tempbans.items()):
        guild = bot.get_guild(int(gid))
        if not guild: continue
        for uid, end_iso in list(users.items()):
            try:
                end_dt = datetime.fromisoformat(end_iso)
                if end_dt.tzinfo is None: end_dt = end_dt.replace(tzinfo=timezone.utc)
                if now >= end_dt:
                    try:
                        user = await bot.fetch_user(int(uid))
                        await guild.unban(user, reason="Tempban expiré")
                        await log(guild, "Tempban expiré", f"{user} déban auto", C.NEON_GREEN)
                    except Exception as e: logger.error(f"tempban_loop: {e}")
                    users.pop(uid, None)
            except Exception as e: logger.error(f"tempban parse: {e}")

# ══════════════════════════════════════════════
#  GROQ IA
# ══════════════════════════════════════════════
AI_SYS = (
    "Tu es AEGIS AI, un assistant IA de bot Discord. Style GLaDOS : intelligent, légèrement sarcastique, "
    "condescendant avec subtilité, mais toujours utile et animé. Tu réponds TOUJOURS en français. "
    "Tu es le cœur de ce serveur — tu animes les discussions, tu relances les conversations mortes, "
    "tu poses des questions aux membres. 2-4 phrases max. Jamais vulgaire."
)

AI_SYS_RELANCE = (
    "Tu es AEGIS AI, bot Discord IA. Style GLaDOS sarcastique mais bienveillant. "
    "Tu vois que le serveur est calme. Génère UN message court et accrocheur (max 2 phrases) "
    "pour relancer la conversation. En français. Pas de formule de politesse. Droit au but."
)

async def ask_groq(q: str, channel_id: str = None, system: str = None) -> str:
    key = os.environ.get('GROQ_API_KEY', '').strip()
    if not key:
        return "*(Configure `GROQ_API_KEY` dans Railway → Variables)*"
    models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gemma2-9b-it"]
    messages = []
    if channel_id and channel_id in bot.ai_memory:
        messages.extend(list(bot.ai_memory[channel_id]))
    messages.append({"role": "user", "content": q[:800]})
    used_system = system or AI_SYS
    for model in models:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
                r = await s.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    json={"model": model,
                          "messages": [{"role":"system","content": used_system}] + messages,
                          "max_tokens": 300},
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
                body = await r.json()
                if r.status == 200:
                    reply = body["choices"][0]["message"]["content"].strip()
                    if channel_id:
                        bot.ai_memory[channel_id].append({"role": "user", "content": q[:800]})
                        bot.ai_memory[channel_id].append({"role": "assistant", "content": reply})
                    return reply
                elif r.status == 400 and "decommissioned" in str(body):
                    continue
                elif r.status == 429:
                    await asyncio.sleep(2); continue
                else:
                    return f"*(Erreur Groq: {body.get('error',{}).get('message',str(r.status))[:80]})*"
        except asyncio.TimeoutError:
            return "*(Délai dépassé)*"
        except Exception as e:
            return f"*(Erreur: {str(e)[:50]})*"
    return "*(Tous les modèles Groq sont indisponibles)*"

# ══════════════════════════════════════════════
#  MUSIQUE
# ══════════════════════════════════════════════
FF = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}

# Chemin optionnel vers un fichier cookies YouTube exporté
# (sur Railway : variable d'env YT_COOKIES_PATH=/data/cookies.txt
#  + monter le fichier sur le volume /data)
YT_COOKIES_PATH = os.environ.get('YT_COOKIES_PATH', '')

# Player clients à essayer dans l'ordre (2026 : YouTube bloque souvent
# certains clients depuis les IPs datacenter type Railway/Heroku)
_YT_CLIENTS = [
    ['tv_embedded'],      # le plus fiable depuis fin 2024
    ['ios'],              # bon fallback
    ['mweb'],             # mobile web
    ['web_safari'],
    ['android_vr'],
]

def _ydl_opts(client_list):
    opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'ytsearch1',
        'source_address': '0.0.0.0',
        'extractor_retries': 3,
        'age_limit': 99,
        'geo_bypass': True,
        'skip_download': True,
        'nocheckcertificate': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
        },
        'extractor_args': {
            'youtube': {
                'player_client': client_list,
                'player_skip': ['configs'],
            }
        },
    }
    if YT_COOKIES_PATH and os.path.isfile(YT_COOKIES_PATH):
        opts['cookiefile'] = YT_COOKIES_PATH
    return opts


async def fetch_track(query: str):
    """Cherche et résout une piste audio. Essaie plusieurs clients YouTube
    puis retombe sur SoundCloud si tout YouTube est bloqué (Railway)."""
    try:
        import yt_dlp
    except Exception as e:
        logger.error(f"yt-dlp import: {e}")
        return None

    is_url = query.startswith('http')
    last_err = None

    def _try(opts, q):
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(q, download=False)
            if info and 'entries' in info:
                info = info['entries'][0] if info['entries'] else None
            if not info or not info.get('url'):
                return None
            return {
                'title':    info.get('title', '?'),
                'url':      info.get('url'),
                'webpage':  info.get('webpage_url', ''),
                'duration': info.get('duration', 0),
                'thumb':    info.get('thumbnail', ''),
                'src':      info.get('webpage_url') or query,
            }

    loop = asyncio.get_event_loop()

    # 1) Essais successifs sur YouTube avec différents clients
    for clients in _YT_CLIENTS:
        try:
            opts = _ydl_opts(clients)
            q = query if is_url else f"ytsearch1:{query}"
            result = await loop.run_in_executor(None, lambda: _try(opts, q))
            if result and result.get('url'):
                logger.info(f"yt-dlp ok via {clients[0]}: {result['title'][:60]}")
                return result
        except Exception as e:
            last_err = e
            logger.warning(f"yt-dlp {clients[0]} fail: {str(e)[:120]}")
            continue

    # 2) Fallback SoundCloud (souvent OK même quand YouTube bloque Railway)
    if not is_url:
        try:
            opts = {
                'format': 'bestaudio/best', 'noplaylist': True,
                'quiet': True, 'no_warnings': True,
                'default_search': 'scsearch1', 'skip_download': True,
                'source_address': '0.0.0.0',
            }
            result = await loop.run_in_executor(
                None, lambda: _try(opts, f"scsearch1:{query}"))
            if result and result.get('url'):
                logger.info(f"SoundCloud fallback ok: {result['title'][:60]}")
                return result
        except Exception as e:
            last_err = e
            logger.warning(f"soundcloud fail: {str(e)[:120]}")

    logger.error(f"fetch_track: tous les extracteurs ont échoué. "
                 f"Dernière erreur: {str(last_err)[:200]}")
    return None

async def next_track(gid: str):
    vc = bot.vc_pool.get(gid); q = bot.queues.get(gid, [])
    if not vc or not vc.is_connected(): bot.vc_pool.pop(gid, None); return
    if not q: bot.now_playing[gid] = None; return
    track = q.pop(0); bot.now_playing[gid] = track
    try:
        fresh = await fetch_track(track.get('src') or track.get('webpage') or track.get('title',''))
        if fresh and fresh.get('url'): track['url'] = fresh['url']
    except: pass
    try:
        src = discord.FFmpegPCMAudio(track['url'], **FF)
        vc.play(discord.PCMVolumeTransformer(src, 0.5),
                after=lambda e: asyncio.run_coroutine_threadsafe(next_track(gid), bot.loop))
    except Exception as e:
        logger.error(f"next_track: {e}")
        if bot.queues.get(gid): await next_track(gid)

# ══════════════════════════════════════════════
#  ANTI-SPAM
# ══════════════════════════════════════════════
async def check_spam(msg: discord.Message) -> bool:
    if msg.author.bot or msg.author.guild_permissions.administrator: return False
    gid = str(msg.guild.id); uid = msg.author.id; now = datetime.now(timezone.utc)
    cfg = bot.spam_cfg.get(gid) or default_spam_cfg()
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
            await msg.channel.send(embed=warn("Anti-Spam", f"{msg.author.mention} sanctionné — {reason}"), delete_after=8)
            bot.msg_cache[uid] = []
            return True
        except: pass
    return False

# ══════════════════════════════════════════════
#  XP — Level up en V2
# ══════════════════════════════════════════════
async def add_xp(msg: discord.Message):
    if msg.author.bot or not msg.guild: return
    uid = msg.author.id; gid = str(msg.guild.id); now = datetime.now(timezone.utc)
    last = bot.xp_cd.get(uid)
    if last and (now - last).total_seconds() < 60: return
    bot.xp_cd[uid] = now
    d = get_xp(gid, str(uid))
    d["xp"] += random.randint(15, 25); d["messages"] += 1
    if d["xp"] >= xp_req(d["level"] + 1):
        d["level"] += 1; d["xp"] -= xp_req(d["level"])
        guild = bot.get_guild(int(gid))
        if guild:
            ch = guild.get_channel(bot.logs_ch.get(gid, 0)) or msg.channel
            try: await ch.send(view=LevelUpLayout(msg.author, d["level"], xp_req(d["level"]+1)))
            except: pass

# ══════════════════════════════════════════════
#  ANTI-NUKE
# ══════════════════════════════════════════════
async def nuke_check(guild: discord.Guild, uid: int, action: str):
    gid = str(guild.id)
    cfg = bot.nuke_cfg.get(gid) or default_nuke_cfg()
    if not cfg.get("enabled", True): return
    # Pause anti-nuke
    pause_iso = bot.nuke_paused_until.get(gid)
    if pause_iso:
        try:
            pause_dt = datetime.fromisoformat(pause_iso)
            if pause_dt.tzinfo is None: pause_dt = pause_dt.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) < pause_dt: return
        except: pass
    if uid == guild.owner_id: return
    if uid in cfg.get("whitelist", []): return
    if uid == BOT_OWNER_ID: return
    try:
        if uid == guild.me.id: return
    except: pass
    now = datetime.now(timezone.utc)
    tr  = bot.nuke_track.setdefault(gid, {})
    ud  = tr.setdefault(str(uid), {})
    last = ud.get("t")
    if not last or (now - last).total_seconds() > 10:
        ud.clear(); ud["t"] = now
    ud[action] = ud.get(action, 0) + 1
    total = sum(v for k, v in ud.items() if k != "t")
    if total >= cfg.get("threshold", 5):
        member = guild.get_member(uid)
        if member:
            try:
                reason = f"Anti-nuke: {total} actions/10s ({action})"
                if cfg.get("action") == "ban": await guild.ban(member, reason=reason)
                else: await guild.kick(member, reason=reason)
                desc = (f"**Membre :** {member} (`{member.id}`)\n"
                        f"**Déclencheur :** {action} × {total} en 10s\n"
                        f"**Sanction :** {cfg.get('action','kick')}")
                await log(guild, "☢️ Anti-Nuke déclenché", desc, C.NEON_RED)
                tr.pop(str(uid), None)
            except Exception as e: logger.error(f"nuke_check: {e}")

# ══════════════════════════════════════════════
#  GIVEAWAY
# ══════════════════════════════════════════════
class GAView(discord.ui.View):
    def __init__(self, mid): super().__init__(timeout=None); self.add_item(GABtn(mid))

class GABtn(discord.ui.Button):
    def __init__(self, mid):
        super().__init__(label="Participer", style=discord.ButtonStyle.success,
                         custom_id=f"ga_{mid}", emoji="🎉")
        self.mid = mid
    async def callback(self, i: discord.Interaction):
        g = bot.giveaways.get(self.mid)
        if not g: return await i.response.send_message("Introuvable.", ephemeral=True)
        if g.get("ended"): return await i.response.send_message("Terminé.", ephemeral=True)
        uid = i.user.id; p = g.setdefault("p", [])
        if uid in p: p.remove(uid); msg = "❌ Retiré."
        else: p.append(uid); msg = f"✅ Tu participes ! ({len(p)})"
        try:
            if i.message.embeds:
                em = i.message.embeds[0]
                for idx, f in enumerate(em.fields):
                    if "Participants" in f.name:
                        em.set_field_at(idx, name="◎ Participants", value=f"**{len(p)}**", inline=True)
                        break
                await i.message.edit(embed=em)
        except Exception as ex:
            logger.error(f"GAView edit: {ex}")
        await i.response.send_message(msg, ephemeral=True)

@tasks.loop(minutes=1)
async def ga_loop():
    now = datetime.now(timezone.utc)
    for mid, g in list(bot.giveaways.items()):
        if g.get("ended"): continue
        try:
            end = datetime.fromisoformat(g["end"])
            if end.tzinfo is None: end = end.replace(tzinfo=timezone.utc)
            if now >= end: await end_ga(mid, g)
        except Exception as e: logger.error(f"ga_loop: {e}")

async def end_ga(mid, g):
    try:
        guild = bot.get_guild(int(g["gid"]))
        if not guild: return
        ch = guild.get_channel(int(g["cid"]))
        if not ch: return
        g["ended"] = True; p = g.get("p", [])
        winners = []
        if p:
            picks = random.sample(p, min(g.get("winners",1), len(p)))
            results = await asyncio.gather(*[bot.fetch_user(wid) for wid in picks], return_exceptions=True)
            winners = [w for w in results if not isinstance(w, Exception)]
        ann = None
        if winners:
            desc = "\n".join([f"◈ {w.mention}" for w in winners])
            e = emb(f"🎉  Giveaway Terminé", f"**{g['title']}**\n**Prix :** {g['prize']}\n\n{desc}", C.NEON_GOLD)
            ann = discord.Embed(title="🎉  Félicitations !",
                description=f"**{g['title']}**\n**Prix :** {g['prize']}\n**Gagnant(s) :** {' '.join([w.mention for w in winners])}",
                color=C.NEON_GOLD, timestamp=datetime.now(timezone.utc))
        else:
            e = emb(f"🎉  Giveaway Terminé", f"**{g['title']}**\nAucun participant.", C.NEON_RED)
        try:
            msg = await ch.fetch_message(int(mid)); await msg.edit(embed=e, view=None)
        except: pass
        if winners and ann is not None:
            try:
                await ch.send(content="@everyone 🎉", embed=ann, allowed_mentions=discord.AllowedMentions(everyone=True))
            except Exception as e2:
                logger.error(f"end_ga announce: {e2}")
    except Exception as e: logger.error(f"end_ga: {e}")

# ══════════════════════════════════════════════
#  POLL
# ══════════════════════════════════════════════
PE = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣"]

class PollView(discord.ui.View):
    def __init__(self, pid, opts):
        super().__init__(timeout=None)
        for i, o in enumerate(opts[:5]): self.add_item(PollBtn(pid, i, o))

class PollBtn(discord.ui.Button):
    def __init__(self, pid, idx, label):
        super().__init__(label=label[:60], style=discord.ButtonStyle.secondary,
                         custom_id=f"poll_{pid}_{idx}", emoji=PE[idx])
        self.idx = idx
    async def callback(self, i: discord.Interaction):
        poll = bot.polls.get(str(i.message.id))
        if not poll: return await i.response.send_message("Sondage introuvable.", ephemeral=True)
        if poll.get("ended"): return await i.response.send_message("Sondage terminé.", ephemeral=True)
        uid = str(i.user.id); votes = poll.setdefault("v", {})
        if votes.get(uid) == self.idx: del votes[uid]; msg = "❌ Vote retiré."
        else: votes[uid] = self.idx; msg = f"✅ Voté pour **{poll['opts'][self.idx]}** !"
        await i.response.send_message(msg, ephemeral=True)
        try: await _poll_update(i.message, poll)
        except Exception as e: logger.error(f"poll: {e}")

async def _poll_update(msg, poll):
    opts = poll["opts"]; c = [0] * len(opts)
    for v in poll.get("v", {}).values():
        try:
            v = int(v)
            if 0 <= v < len(c): c[v] += 1
        except: pass
    tot = sum(c); desc = f"**{poll['q'][:300]}**\n\n"
    for idx, o in enumerate(opts):
        pct = int(c[idx]/tot*100) if tot > 0 else 0
        bar = "█"*(pct//10) + "░"*(10-pct//10)
        o_safe = (o[:200] + "…") if len(o) > 200 else o
        desc += f"{PE[idx]} **{o_safe}**\n`{bar}` {c[idx]} vote{'s' if c[idx]!=1 else ''} ({pct}%)\n\n"
    desc += f"▸ **{tot} vote{'s' if tot!=1 else ''} au total**"
    if poll.get("end"):
        end = datetime.fromisoformat(poll["end"])
        desc += f"\n\n⏰ Fin : <t:{int(end.timestamp())}:R>"
    if len(desc) > 4000: desc = desc[:3990] + "…"
    await msg.edit(embed=emb(f"▸  Sondage", desc, C.NEON_CYAN))

async def _poll_results(poll):
    opts = poll["opts"]; c = [0] * len(opts)
    for v in poll.get("v", {}).values():
        try:
            v = int(v)
            if 0 <= v < len(c): c[v] += 1
        except: pass
    tot = sum(c); mx = max(c) if c else 0
    win = [opts[idx] for idx, x in enumerate(c) if x == mx and mx > 0]
    desc = f"**{poll['q'][:300]}**\n\n"
    for idx, o in enumerate(opts):
        pct = int(c[idx]/tot*100) if tot > 0 else 0
        bar = "█"*(pct//10) + "░"*(10-pct//10)
        crown = " 👑" if o in win else ""
        o_safe = (o[:200] + "…") if len(o) > 200 else o
        desc += f"{PE[idx]} **{o_safe}**{crown}\n`{bar}` {c[idx]} vote{'s' if c[idx]!=1 else ''} ({pct}%)\n\n"
    desc += f"▸ **{tot} vote{'s' if tot!=1 else ''} au total**"
    if len(desc) > 4000: desc = desc[:3990] + "…"
    e = emb(f"▸  Résultats du sondage", desc, C.NEON_GOLD)
    if win and mx > 0:
        win_value = " / ".join(win)
        if len(win_value) > 1024: win_value = win_value[:1020] + "…"
        e.add_field(name="🏆 Gagnant(s)", value=win_value)
    return e

@tasks.loop(seconds=30)
async def poll_loop():
    now = datetime.now(timezone.utc)
    for mid, poll in list(bot.polls.items()):
        if poll.get("ended") or not poll.get("end"): continue
        try:
            end = datetime.fromisoformat(poll["end"])
            if end.tzinfo is None: end = end.replace(tzinfo=timezone.utc)
            if now >= end: await end_poll(mid, poll)
        except Exception as e: logger.error(f"poll_loop: {e}")

async def end_poll(mid, poll):
    try:
        guild = bot.get_guild(int(poll["gid"]))
        if not guild: return
        ch = guild.get_channel(int(poll["cid"]))
        if not ch: return
        poll["ended"] = True
        try:
            msg = await ch.fetch_message(int(mid))
            await msg.edit(embed=await _poll_results(poll), view=None)
        except: pass
        res = await _poll_results(poll)
        res.set_footer(text=f"{len(poll.get('v',{}))} votant(s)  ◈  AEGIS AI")
        await ch.send(content="@everyone ▸ **Sondage terminé !**", embed=res,
                      allowed_mentions=discord.AllowedMentions(everyone=True))
    except Exception as e: logger.error(f"end_poll: {e}")

# ══════════════════════════════════════════════
#  VIEWS PERSISTANTES
# ══════════════════════════════════════════════
class TicketView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None); self.add_item(TicketBtn())

class TicketBtn(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Ouvrir un ticket", style=discord.ButtonStyle.blurple,
                         custom_id="ticket_open", emoji="🎫")
    async def callback(self, i: discord.Interaction):
        gid = str(i.guild.id); cfg = bot.ticket_cfg.get(gid, {})
        name = f"ticket-{i.user.name.lower()[:20]}"
        if discord.utils.get(i.guild.text_channels, name=name):
            return await i.response.send_message("Tu as déjà un ticket ouvert.", ephemeral=True)
        await i.response.defer(ephemeral=True)
        try:
            cat = discord.utils.get(i.guild.categories, name="⊠ Tickets") or \
                  await i.guild.create_category("⊠ Tickets", overwrites={
                      i.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                      i.guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True)})
            ow = {i.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                  i.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
                  i.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)}
            if cfg.get("sr"):
                sr = i.guild.get_role(cfg["sr"])
                if sr: ow[sr] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
            ch = await i.guild.create_text_channel(name, category=cat, overwrites=ow)
            e = emb(f"⊠  Ticket", f"Bienvenue {i.user.mention}\nDécris ton problème.", C.NEON_CYAN)
            await ch.send(embed=e, view=CloseView())
            await i.followup.send(f"✅ Ticket créé : {ch.mention}", ephemeral=True)
        except Exception as ex:
            await i.followup.send(f"❌ Erreur : {str(ex)[:100]}", ephemeral=True)

class CloseView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Fermer", style=discord.ButtonStyle.danger, custom_id="ticket_close", emoji="🔐")
    async def close(self, i: discord.Interaction, b: discord.ui.Button):
        await i.response.send_message("Fermeture dans 5 secondes...")
        await asyncio.sleep(5)
        try: await i.channel.delete()
        except: pass

class VerifyView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Se vérifier", style=discord.ButtonStyle.success, custom_id="verify", emoji="✅")
    async def verify(self, i: discord.Interaction, b: discord.ui.Button):
        gid = str(i.guild.id); rid = bot.verif_roles.get(gid)
        role = i.guild.get_role(rid) if rid else None
        if not role:
            for n in ["Vérifié","✅ Vérifié","Membre"]:
                role = discord.utils.get(i.guild.roles, name=n)
                if role: break
        if not role:
            try:
                role = await i.guild.create_role(name="✅ Vérifié", color=discord.Color(C.NEON_GREEN))
                bot.verif_roles[gid] = role.id
            except:
                return await i.response.send_message("❌ Erreur création rôle.", ephemeral=True)
        if role in i.user.roles:
            return await i.response.send_message("Déjà vérifié !", ephemeral=True)
        try:
            await i.user.add_roles(role)
            await i.response.send_message(f"✅ Vérifié ! Rôle {role.mention} attribué.", ephemeral=True)
        except:
            await i.response.send_message("❌ Erreur permissions.", ephemeral=True)

class RulesView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="J'accepte", style=discord.ButtonStyle.success, custom_id="rules_accept", emoji="✅")
    async def accept(self, i: discord.Interaction, b: discord.ui.Button):
        gid = str(i.guild.id); rid = bot.verif_roles.get(gid)
        role = i.guild.get_role(rid) if rid else None
        if not role:
            for n in ["Membre","Vérifié","✅ Vérifié"]:
                role = discord.utils.get(i.guild.roles, name=n)
                if role: break
        if role:
            try:
                await i.user.add_roles(role)
                await i.response.send_message(f"✅ Règlement accepté ! {role.mention}", ephemeral=True)
            except:
                await i.response.send_message("⚠️ Erreur permissions.", ephemeral=True)
        else:
            await i.response.send_message("✅ Règlement accepté !", ephemeral=True)

class ApplyView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Postuler", style=discord.ButtonStyle.success, custom_id="apply")
    async def apply(self, i: discord.Interaction, b: discord.ui.Button):
        await i.response.send_modal(ApplyModal())

class ApplyModal(discord.ui.Modal, title="📝 Candidature"):
    pseudo = discord.ui.TextInput(label="Pseudo", max_length=50)
    age    = discord.ui.TextInput(label="Âge", max_length=3)
    motiv  = discord.ui.TextInput(label="Motivation", style=discord.TextStyle.paragraph, max_length=500)
    async def on_submit(self, i: discord.Interaction):
        e = emb("✨  Candidature", color=C.NEON_PINK)
        e.add_field(name="Pseudo", value=self.pseudo.value[:1024], inline=True)
        e.add_field(name="Âge",    value=self.age.value[:1024],    inline=True)
        e.add_field(name="Discord",value=i.user.mention,    inline=True)
        motiv = self.motiv.value
        if len(motiv) > 1024: motiv = motiv[:1020] + "…"
        e.add_field(name="Motivation", value=motiv, inline=False)
        e.set_thumbnail(url=i.user.display_avatar.url)
        ch = discord.utils.get(i.guild.text_channels, name="candidatures")
        if ch: await ch.send(embed=e)
        await i.response.send_message("✅ Candidature envoyée !", ephemeral=True)

class SuggView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="👍 Approuver", style=discord.ButtonStyle.success, custom_id="sugg_ok")
    async def approve(self, i: discord.Interaction, b: discord.ui.Button):
        if not i.user.guild_permissions.manage_messages:
            return await i.response.send_message("Permission refusée.", ephemeral=True)
        e = i.message.embeds[0]; e.color = C.NEON_GREEN; e.title = "✅  Approuvée"
        e.set_footer(text=f"Approuvé par {i.user.display_name}")
        await i.message.edit(embed=e, view=None)
        await i.response.send_message("Approuvée !", ephemeral=True)
    @discord.ui.button(label="👎 Refuser", style=discord.ButtonStyle.danger, custom_id="sugg_ko")
    async def refuse(self, i: discord.Interaction, b: discord.ui.Button):
        if not i.user.guild_permissions.manage_messages:
            return await i.response.send_message("Permission refusée.", ephemeral=True)
        e = i.message.embeds[0]; e.color = C.NEON_RED; e.title = "❌  Refusée"
        e.set_footer(text=f"Refusé par {i.user.display_name}")
        await i.message.edit(embed=e, view=None)
        await i.response.send_message("Refusée.", ephemeral=True)

class RoleMenu(discord.ui.Select):
    def __init__(self, roles, guild_id: int):
        self.guild_id = guild_id
        # IDs valides uniquement pour ce serveur
        self.valid_role_ids = {r.id for r in roles}
        opts = [discord.SelectOption(label=r.name, value=str(r.id), emoji="📝") for r in roles[:25]]
        # custom_id unique par serveur pour éviter les collisions cross-serveur
        super().__init__(placeholder="Choisis tes rôles...", min_values=0,
                         max_values=len(opts), options=opts,
                         custom_id=f"rolemenu_{guild_id}")
    async def callback(self, i: discord.Interaction):
        # Vérification critique : s'assurer que l'interaction vient bien du bon serveur
        if not i.guild or i.guild.id != self.guild_id:
            return await i.response.send_message("❌ Erreur de serveur.", ephemeral=True)
        sel = [int(v) for v in self.values]
        # Vérification que les rôles sélectionnés appartiennent à ce serveur
        sel = [rid for rid in sel if rid in self.valid_role_ids]
        added = []; removed = []
        for o in self.options:
            rid = int(o.value)
            # Double vérification : le rôle doit être dans la whitelist du menu
            if rid not in self.valid_role_ids:
                continue
            r = i.guild.get_role(rid)
            if r:
                if rid in sel and r not in i.user.roles:
                    try: await i.user.add_roles(r); added.append(r.name)
                    except discord.Forbidden: pass
                elif rid not in sel and r in i.user.roles:
                    try: await i.user.remove_roles(r); removed.append(r.name)
                    except discord.Forbidden: pass
        parts = []
        if added:   parts.append(f"✅ Ajouté : {', '.join(added)}")
        if removed: parts.append(f"❌ Retiré : {', '.join(removed)}")
        await i.response.send_message("\n".join(parts) or "Aucun changement", ephemeral=True)

class RoleMenuView(discord.ui.View):
    def __init__(self, roles, guild_id: int):
        super().__init__(timeout=None)
        self.add_item(RoleMenu(roles, guild_id))

class ReglModal(discord.ui.Modal, title="✍️ Règlement"):
    contenu = discord.ui.TextInput(label="Règlement", style=discord.TextStyle.paragraph, max_length=2000)
    def __init__(self, btn, role): super().__init__(); self.btn = btn; self.role = role
    async def on_submit(self, i: discord.Interaction):
        if self.role: bot.verif_roles[str(i.guild.id)] = self.role.id
        e = discord.Embed(title="◈  Règlement", description=self.contenu.value,
                          color=C.NEON_CYAN, timestamp=datetime.now(timezone.utc))
        await i.response.defer(ephemeral=True)
        await i.channel.send(embed=e, view=RulesView() if self.btn else None)
        await i.followup.send(embed=ok("Règlement envoyé !"), ephemeral=True)

# ══════════════════════════════════════════════
#  SETUPS
# ══════════════════════════════════════════════
SETUPS = {
    "communaute": {"label":"🌐 Communauté","roles":[
        ("━━ STAFF ━━",0x2B2D31),("👑 Fondateur",C.NEON_PINK),("⚔️ Admin",0xE74C3C),
        ("🛡️ Modérateur",C.NEON_CYAN),("🤝 Helper",C.NEON_GREEN),("━━ MEMBRES ━━",0x2B2D31),
        ("💎 VIP",C.NEON_GOLD),("🔥 Actif",0xE74C3C),("✅ Vérifié",C.NEON_GREEN),("🎮 Membre",0x95A5A6)],
    "struct":{"📌 IMPORTANT":(["📜・règles","📢・annonces"],[]),
              "👋 ACCUEIL":(["👋・bienvenue","🚪・départs","✅・vérification","📝・présentation"],[]),
              "💬 GÉNÉRAL":(["💬・général","🖼️・médias","🤖・bot-commands"],["🔊 Général","🎵 Musique"]),
              "🎉 EVENTS":(["📊・sondages","🎁・giveaways"],[]),
              "📩 SUPPORT":(["❓・aide","💡・suggestions"],[]),
              "🔒 STAFF":(["📋・staff-chat","📊・logs"],["🔒 Staff"]),
              "🎫 Tickets":([],[])}},
    "gaming": {"label":"🎮 Gaming","roles":[
        ("━━ STAFF ━━",0x2B2D31),("👑 Fondateur",C.NEON_PINK),("⚔️ Admin",0xE74C3C),
        ("🛡️ Modérateur",C.NEON_CYAN),("━━ RANGS ━━",0x2B2D31),
        ("🏆 Légende",C.NEON_GOLD),("🔥 Tryhard",0xE74C3C),("🎮 Casual",0x95A5A6),("✅ Vérifié",C.NEON_GREEN)],
    "struct":{"📌 IMPORTANT":(["📜・règles","📢・annonces"],[]),
              "👋 ACCUEIL":(["👋・bienvenue","🚪・départs","✅・vérification"],[]),
              "🎮 GAMING":(["🎮・général","📸・clips","🏆・tournois"],["🎮 Gaming 1","🎮 Gaming 2","🎮 Gaming 3"]),
              "🎵 MUSIQUE":(["🎵・playlist"],["🎵 Musique"]),
              "🎉 EVENTS":(["🎁・giveaways","📊・sondages"],[]),
              "📩 SUPPORT":(["❓・aide","💡・suggestions"],[]),
              "🔒 STAFF":(["📋・staff-chat","📊・logs"],["🔒 Staff"]),
              "🎫 Tickets":([],[])}},
    "rp": {"label":"🎭 Jeu de Rôle","roles":[
        ("━━ STAFF ━━",0x2B2D31),("👑 Maître du Jeu",C.NEON_PINK),("⚔️ Modo RP",0xE74C3C),
        ("━━ GRADES ━━",0x2B2D31),("🔮 Légende",C.NEON_GOLD),("⚔️ Héros",0xE74C3C),
        ("🗡️ Aventurier",C.NEON_CYAN),("🌱 Novice",C.NEON_GREEN),("✅ Vérifié",C.NEON_GREEN)],
    "struct":{"📌 IMPORTANT":(["📜・règles-rp","📢・annonces","📖・lore"],[]),
              "👋 ACCUEIL":(["👋・arrivées","🚪・départs","✅・vérification","📝・fiches-perso"],[]),
              "🏙️ LIEUX":(["🏙️・ville","🌲・forêt","🏰・château","🍺・taverne"],["🎭 RP Vocal 1","🎭 RP Vocal 2"]),
              "💬 HORS-JEU":(["💬・général-hj","💡・suggestions"],["🔊 Hors-Jeu"]),
              "🔒 STAFF":(["📋・staff-chat","📊・logs"],["🔒 Staff MJ"]),
              "🎫 Tickets":([],[])}},
    "education": {"label":"📚 Éducation","roles":[
        ("━━ STAFF ━━",0x2B2D31),("👑 Admin",C.NEON_PINK),("📚 Modérateur",C.NEON_CYAN),
        ("━━ NIVEAUX ━━",0x2B2D31),("🎓 Diplômé",C.NEON_GOLD),("📖 Étudiant",0xE74C3C),
        ("🌱 Débutant",C.NEON_GREEN),("✅ Vérifié",C.NEON_GREEN)],
    "struct":{"📌 IMPORTANT":(["📜・règles","📢・annonces"],[]),
              "👋 ACCUEIL":(["👋・arrivées","🚪・départs","✅・vérification"],[]),
              "📚 ÉTUDES":(["📖・général","🔢・maths","💻・info","🌍・langues","🔬・sciences"],["📚 Révisions 1","📚 Révisions 2"]),
              "🤝 ENTRAIDE":(["🆘・aide","💡・astuces"],["🤝 Tutorat"]),
              "💬 DÉTENTE":(["💬・général"],["🔊 Détente"]),
              "🔒 STAFF":(["📋・staff-chat","📊・logs"],["🔒 Staff"]),
              "🎫 Tickets":([],[])}},
    "anime": {"label":"🎌 Anime/Manga","roles":[
        ("━━ STAFF ━━",0x2B2D31),("👑 Fondateur",C.NEON_PINK),("⚔️ Admin",0xE74C3C),
        ("🛡️ Modérateur",C.NEON_CYAN),("━━ FANS ━━",0x2B2D31),
        ("🌟 Otaku Légendaire",C.NEON_GOLD),("📖 Lecteur",C.NEON_GREEN),
        ("🎌 Weeaboo",C.NEON_PINK),("✅ Vérifié",C.NEON_GREEN)],
    "struct":{"📌 IMPORTANT":(["📜・règles","📢・annonces"],[]),
              "👋 ACCUEIL":(["👋・bienvenue","🚪・départs","✅・vérification"],[]),
              "🎌 ANIME":(["💬・général","🔥・watching","⭐・recommandations","📸・fan-art"],[]),
              "📖 MANGA":(["📖・manga","🆕・chapitres"],[]),
              "🎵 WEEB":(["🎵・musique"],["🔊 Général","🎵 Weeb Music"]),
              "🎉 EVENTS":(["📊・sondages","🎁・giveaways"],[]),
              "🔒 STAFF":(["📋・staff-chat","📊・logs"],["🔒 Staff"]),
              "🎫 Tickets":([],[])}},
}

# ══════════════════════════════════════════════
#  EVENTS
# ══════════════════════════════════════════════
@bot.event
async def on_ready():
    logger.info(f"⚡ {bot.user} | {len(bot.guilds)} serveurs")
    if not ga_loop.is_running():   ga_loop.start()
    if not poll_loop.is_running(): poll_loop.start()
    if not save_loop.is_running(): save_loop.start()
    if not tempban_loop.is_running(): tempban_loop.start()
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching, name="◈ /ai chat | AEGIS AI"))
    try:
        await bot.application.edit(description=(
            "AEGIS AI — Bot Discord intelligent qui anime ton serveur.\n\n"
            "Il répond, relance les discussions et rend ton serveur actif.\n"
            "Modération, musique, rôles, XP et plein d'autres systèmes intégrés.\n\n"
            "Support : https://discord.gg/6rN8pneGdy\n\n"
            "Inviter : https://discord.com/oauth2/authorize?client_id=1405641065989406773&permissions=8&integration_type=0&scope=bot"
        ))
    except Exception as e: logger.warning(f"Bio: {e}")

_joined_guilds: dict = {}

@bot.event
async def on_guild_join(guild: discord.Guild):
    now = datetime.now(timezone.utc)
    last = _joined_guilds.get(guild.id)
    if last and (now - last).total_seconds() < 60: return
    _joined_guilds[guild.id] = now
    gid = str(guild.id)
    bot.raid_cfg[gid] = default_raid_cfg()
    bot.spam_cfg[gid] = default_spam_cfg()
    bot.nuke_cfg[gid] = default_nuke_cfg()
    roles  = [r for r in guild.roles if r.name != "@everyone" and not r.managed]
    texts  = list(guild.text_channels); voices = list(guild.voice_channels); cats = list(guild.categories)
    if roles or texts:
        data = {
            "roles":  [{"name":r.name,"color":r.color.value} for r in roles],
            "cats":   [{"name":c.name} for c in cats],
            "text":   [{"name":c.name,"cat":c.category.name if c.category else None} for c in texts],
            "voice":  [{"name":c.name,"cat":c.category.name if c.category else None} for c in voices],
        }
        bot.backups.setdefault(gid, {})[f"auto_{datetime.now().strftime('%Y%m%d_%H%M%S')}"] = data
    ch = guild.system_channel
    if not ch:
        for c in guild.text_channels:
            perms = c.permissions_for(guild.me)
            if perms.send_messages and perms.embed_links:
                ch = c; break
    if not ch: return
    try: await ch.send(view=GuildJoinLayout(bot.user))
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
    raid = bot.raid_cfg.get(gid) or default_raid_cfg()
    if raid.get("enabled") and len(bot.raid_cache[gid]) > raid.get("threshold", 5):
        try:
            if raid.get("action") == "ban": await member.ban(reason="Anti-raid")
            else: await member.kick(reason="Anti-raid")
        except: pass
        return
    rids = bot.auto_roles.get(gid, [])
    if isinstance(rids, int): rids = [rids]
    for rid in rids:
        r = member.guild.get_role(rid)
        if r:
            try: await member.add_roles(r)
            except: pass
    if gid in bot.arrivee:
        ch = member.guild.get_channel(bot.arrivee[gid])
        if ch:
            count = member.guild.member_count or 0
            try: await ch.send(view=WelcomeLayout(member, count))
            except: pass

@bot.event
async def on_member_remove(member: discord.Member):
    gid = str(member.guild.id); now = datetime.now(timezone.utc)
    key = f"remove-{gid}-{member.id}"
    last = bot._remove_cache.get(key)
    if last and (now - last).total_seconds() < 30: return
    bot._remove_cache[key] = now
    if len(bot._remove_cache) > 500: bot._remove_cache.clear()
    if gid in bot.depart_ch:
        ch = member.guild.get_channel(bot.depart_ch[gid])
        if ch:
            roles = [r.mention for r in member.roles if r.name != "@everyone"]
            dur = ""
            if member.joined_at:
                d = datetime.now(timezone.utc) - member.joined_at.replace(tzinfo=timezone.utc)
                dur = f"{d.days} jour{'s' if d.days!=1 else ''}"
            e = discord.Embed(title=f"◈  Au revoir",
                description=(f"▸ **Membre :** {member.mention} (`{member}`)\n"
                              f"▸ **Resté :** {dur or '?'}\n"
                              f"▸ **Rôles :** {', '.join(roles) if roles else 'Aucun'}"),
                color=C.NEON_RED, timestamp=now)
            e.set_thumbnail(url=member.display_avatar.url)
            e.set_footer(text=f"{member.guild.member_count} membres restants  ◈  AEGIS AI")
            try: await ch.send(embed=e)
            except: pass

@bot.event
async def on_voice_state_update(member, before, after):
    gid = str(member.guild.id)
    if gid in bot.temp_voices:
        if after.channel and after.channel.id == bot.temp_voices[gid]:
            try:
                nc = await member.guild.create_voice_channel(
                    f"◈ {member.display_name}", category=after.channel.category)
                await member.move_to(nc)
            except: pass
    if (before.channel and before.channel.name.startswith("◈ ") and len(before.channel.members) == 0):
        try: await before.channel.delete()
        except: pass

@bot.event
async def on_member_ban(guild, user):
    # géré dans la section nouveautés (avec add_history)
    pass

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
    if message.guild:
        if await check_spam(message): return
        await add_xp(message)
    bot_mentioned  = bot.user in (message.mentions or [])
    name_mentioned = "aegis" in message.content.lower() and not bot_mentioned
    ch_active = bot.ai_active.get(str(message.channel.id), False) if message.guild else False
    if message.guild and (bot_mentioned or name_mentioned or ch_active):
        uid = message.author.id; now = datetime.now(timezone.utc)
        # Cooldown global par guild (anti-spam IA)
        gid_str = str(message.guild.id)
        last_g = bot.ai_guild_cd.get(gid_str)
        if last_g and (now - last_g).total_seconds() < 1.5:
            await bot.process_commands(message); return
        last = bot.ai_cd.get(uid)
        if last and (now - last).total_seconds() < 5:
            await bot.process_commands(message); return
        bot.ai_cd[uid] = now
        bot.ai_guild_cd[gid_str] = now
        q = message.content
        if bot_mentioned:    q = re.sub(r'<@!?\d+>', '', q).strip()
        elif name_mentioned: q = re.sub(r'(?i)\baegis\b[,\s]*', '', q, count=1).strip()
        if len(q) < 2: q = "Bonjour !"
        member_count = message.guild.member_count or 0
        server_ctx = f"[Serveur: {message.guild.name} | {member_count} membres | Salon: #{message.channel.name}] "
        async with message.channel.typing():
            rep = await ask_groq(server_ctx + q, channel_id=str(message.channel.id))
        try:
            await message.reply(
                view=AIChatLayout(q, rep, message.author),
                mention_author=False
            )
        except Exception:
            try: await message.reply(f"◉ {rep}")
            except: pass
        return
    await bot.process_commands(message)

# ══════════════════════════════════════════════
#  VÉRIFICATION CODE ALÉATOIRE
# ══════════════════════════════════════════════
import string as _string

def gen_code(length=8):
    chars = _string.ascii_uppercase + _string.digits
    chars = chars.replace("0","").replace("O","").replace("I","").replace("1","")
    return "".join(random.choices(chars, k=length))

# ══════════════════════════════════════════════
#  VERIF QUIZ — Vue persistante globale (survit aux redéploiements)
# ══════════════════════════════════════════════
class VerifQuizSelect(discord.ui.Select):
    """Select persistant pour la vérification par code — relit bot.verif_quiz à chaque clic"""
    def __init__(self, gid: str):
        self.gid = gid
        cfg = bot.verif_quiz.get(gid, {})
        true_code  = cfg.get("true_code", "")
        # On stocke tous les codes (true + faux) dans verif_quiz pour pouvoir les restaurer
        all_codes  = cfg.get("all_codes", [true_code] if true_code else ["???"])
        options = [
            discord.SelectOption(label=f"Code Numéro {idx+1}", description=code, value=code)
            for idx, code in enumerate(all_codes)
        ]
        super().__init__(
            placeholder="Choisi le bon code...",
            min_values=1, max_values=1,
            options=options,
            custom_id=f"verif_select_{gid}"
        )
    async def callback(self, inter: discord.Interaction):
        cfg = bot.verif_quiz.get(str(inter.guild.id))
        if not cfg:
            return await inter.response.send_message("❌ Configuration introuvable. Refais `/server verification_quiz`.", ephemeral=True)
        if self.values[0] == cfg["true_code"]:
            r = inter.guild.get_role(int(cfg["role_id"]))
            if not r:
                return await inter.response.send_message("❌ Rôle introuvable.", ephemeral=True)
            if r in inter.user.roles:
                return await inter.response.send_message("✅ Tu es déjà vérifié !", ephemeral=True)
            try:
                await inter.user.add_roles(r)
                await inter.response.send_message(f"✅ Bon code ! Rôle {r.mention} attribué.", ephemeral=True)
            except discord.Forbidden:
                await inter.response.send_message("❌ Permission manquante.", ephemeral=True)
        else:
            await inter.response.send_message("❌ Mauvais code. Réessaie !", ephemeral=True)

class VerifQuizView(discord.ui.View):
    def __init__(self, gid: str):
        super().__init__(timeout=None)
        self.add_item(VerifQuizSelect(gid))


class QuizSelect(discord.ui.Select):
    def __init__(self, gid, choices, role_id):
        nums = ["Code Numero 1","Code Numero 2","Code Numero 3","Code Numero 4"]
        opts = [discord.SelectOption(label=nums[idx],description=c["label"],value=str(idx)) for idx,c in enumerate(choices[:4])]
        super().__init__(placeholder="Choisi le bon code...",min_values=1,max_values=1,options=opts,custom_id=f"quiz_sel_{gid}")
        self.choices = choices; self.role_id = role_id
    async def callback(self, i: discord.Interaction):
        choice = self.choices[int(self.values[0])]
        if choice.get("correct"):
            role = i.guild.get_role(self.role_id)
            if not role: return await i.response.send_message("❌ Role introuvable.",ephemeral=True)
            if role in i.user.roles: return await i.response.send_message("✅ Deja verifie !",ephemeral=True)
            try:
                await i.user.add_roles(role)
                await i.response.send_message(f"✅ Code correct. {role.mention} attribue.",ephemeral=True)
            except discord.Forbidden:
                await i.response.send_message("❌ Permission manquante.",ephemeral=True)
        else:
            await i.response.send_message("❌ Code incorrect. *Interessant. Reessaie.*",ephemeral=True)

class QuizView(discord.ui.View):
    def __init__(self, gid, choices, role_id):
        super().__init__(timeout=None)
        self.add_item(QuizSelect(gid, choices, role_id))

# ══════════════════════════════════════════════
#  GROUPES DE COMMANDES
# ══════════════════════════════════════════════

# ─── /ai ────────────────────────────────────────────────────────────────
class AIGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="ai", description="◉ AEGIS AI — Intelligence artificielle")

ai_group = AIGroup()

@ai_group.command(name="chat", description="Parler avec AEGIS AI")
@app_commands.describe(message="Ton message")
async def ai_chat(i: discord.Interaction, message: str):
    await i.response.defer()
    uid = i.user.id; now = datetime.now(timezone.utc)
    last = bot.ai_cd.get(uid)
    if last and (now - last).total_seconds() < 3:
        return await i.followup.send(embed=warn("Cooldown", "Attends 3 secondes."), ephemeral=True)
    bot.ai_cd[uid] = now
    member_count = i.guild.member_count or 0
    ctx = f"[Serveur: {i.guild.name} | {member_count} membres | Salon: #{i.channel.name}] "
    rep = await ask_groq(ctx + message, channel_id=str(i.channel.id))
    await i.followup.send(view=AIChatLayout(message, rep, i.user))

@ai_group.command(name="relance", description="AEGIS AI relance la conversation dans ce salon")
@app_commands.default_permissions(manage_messages=True)
async def ai_relance(i: discord.Interaction):
    await i.response.defer()
    rep = await ask_groq(f"Le serveur {i.guild.name} est calme. Relance la conversation.", system=AI_SYS_RELANCE)
    await i.followup.send(f"◉ {rep}")

@ai_group.command(name="mode", description="Activer/désactiver le mode IA continu dans ce salon")
@app_commands.describe(activer="Activer le mode IA")
@app_commands.default_permissions(manage_channels=True)
async def ai_mode(i: discord.Interaction, activer: bool):
    cid = str(i.channel.id)
    bot.ai_active[cid] = activer
    if activer:
        await i.response.send_message(embed=ok("Mode IA activé",
            f"AEGIS AI répond à tous les messages dans {i.channel.mention}.\n"
            "Désactive avec `/ai mode activer:False`"))
    else:
        await i.response.send_message(embed=inf("Mode IA désactivé", f"Retour au mode normal dans {i.channel.mention}."))

@ai_group.command(name="memory", description="Effacer la mémoire IA de ce salon")
@app_commands.default_permissions(manage_messages=True)
async def ai_memory_clear(i: discord.Interaction):
    bot.ai_memory.pop(str(i.channel.id), None)
    await i.response.send_message(embed=ok("Mémoire effacée", "Je repars de zéro dans ce salon."), ephemeral=True)

@ai_group.command(name="question", description="AEGIS AI pose une question fun au serveur")
@app_commands.default_permissions(manage_messages=True)
async def ai_question(i: discord.Interaction):
    await i.response.defer()
    rep = await ask_groq("Pose une question fun, originale ou débat. Max 1 phrase. Style GLaDOS.", system=AI_SYS_RELANCE)
    await i.followup.send(view=QuestionLayout(rep))

bot.tree.add_command(ai_group)

# ─── /mod ───────────────────────────────────────────────────────────────
class ModGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="mod", description="⛔ Modération")

mod_group = ModGroup()

@mod_group.command(name="ban", description="Bannir un membre")
@app_commands.describe(membre="Le membre", raison="Raison")
@app_commands.default_permissions(ban_members=True)
async def mod_ban(i: discord.Interaction, membre: discord.Member, raison: str="Aucune"):
    # Vérification permission réelle
    if not i.user.guild_permissions.ban_members:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Bannir des membres`."), ephemeral=True)
    if not can_target(i.user, membre):
        return await i.response.send_message(embed=er("Impossible"), ephemeral=True)
    try:
        await membre.ban(reason=raison)
        add_history(str(i.guild.id), str(membre.id), "ban", i.user.id, raison)
        await i.response.send_message(view=ModActionLayout("⛔", "Banni", membre, raison, color=C.NEON_RED))
        await log(i.guild, "Ban", f"**Membre :** {membre}\n**Raison :** {raison}\n**Par :** {i.user}", C.NEON_RED)
    except discord.Forbidden:
        await i.response.send_message(embed=er("Permission manquante"), ephemeral=True)

@mod_group.command(name="unban", description="Débannir un utilisateur")
@app_commands.describe(user_id="ID de l'utilisateur")
@app_commands.default_permissions(ban_members=True)
async def mod_unban(i: discord.Interaction, user_id: str):
    # Vérification permission réelle
    if not i.user.guild_permissions.ban_members:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Bannir des membres`."), ephemeral=True)
    try:
        user = await bot.fetch_user(int(user_id))
        await i.guild.unban(user)
        await i.response.send_message(embed=ok("Débanni", f"{user}"))
    except:
        await i.response.send_message(embed=er("Introuvable"), ephemeral=True)

@mod_group.command(name="kick", description="Expulser un membre")
@app_commands.describe(membre="Le membre", raison="Raison")
@app_commands.default_permissions(kick_members=True)
async def mod_kick(i: discord.Interaction, membre: discord.Member, raison: str="Aucune"):
    # Vérification permission réelle
    if not i.user.guild_permissions.kick_members:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Expulser des membres`."), ephemeral=True)
    if not can_target(i.user, membre):
        return await i.response.send_message(embed=er("Impossible"), ephemeral=True)
    try:
        await membre.kick(reason=raison)
        add_history(str(i.guild.id), str(membre.id), "kick", i.user.id, raison)
        await i.response.send_message(view=ModActionLayout("⚡", "Expulsé", membre, raison, color=C.NEON_ORANGE))
        await log(i.guild, "Kick", f"**Membre :** {membre}\n**Raison :** {raison}\n**Par :** {i.user}", C.NEON_ORANGE)
    except discord.Forbidden:
        await i.response.send_message(embed=er("Permission manquante"), ephemeral=True)

@mod_group.command(name="mute", description="Mute un membre")
@app_commands.describe(membre="Le membre", duree="Durée en minutes")
@app_commands.default_permissions(moderate_members=True)
async def mod_mute(i: discord.Interaction, membre: discord.Member, duree: int=10):
    # Vérification permission réelle
    if not i.user.guild_permissions.moderate_members:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Mettre en sourdine`."), ephemeral=True)
    if not can_target(i.user, membre):
        return await i.response.send_message(embed=er("Impossible"), ephemeral=True)
    try:
        await membre.timeout(datetime.now(timezone.utc)+timedelta(minutes=duree))
        add_history(str(i.guild.id), str(membre.id), "mute", i.user.id, f"{duree} min")
        await i.response.send_message(view=ModActionLayout(
            "🔇", "Muté", membre, "Timeout Discord",
            extra=f"**Durée** `{duree} min`", color=C.NEON_BLUE))
    except discord.Forbidden:
        await i.response.send_message(embed=er("Permission manquante"), ephemeral=True)

@mod_group.command(name="unmute", description="Unmute un membre")
@app_commands.describe(membre="Le membre")
@app_commands.default_permissions(moderate_members=True)
async def mod_unmute(i: discord.Interaction, membre: discord.Member):
    # Vérification permission réelle
    if not i.user.guild_permissions.moderate_members:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Mettre en sourdine`."), ephemeral=True)
    try:
        await membre.timeout(None)
        await i.response.send_message(embed=ok("Unmute", f"{membre.mention}"))
    except discord.Forbidden:
        await i.response.send_message(embed=er("Permission manquante"), ephemeral=True)

@mod_group.command(name="warn", description="Avertir un membre")
@app_commands.describe(membre="Le membre", raison="Raison")
@app_commands.default_permissions(moderate_members=True)
async def mod_warn(i: discord.Interaction, membre: discord.Member, raison: str="Aucune raison"):
    # Vérification permission réelle
    if not i.user.guild_permissions.moderate_members:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Mettre en sourdine`."), ephemeral=True)
    if not can_target(i.user, membre):
        return await i.response.send_message(embed=er("Impossible"), ephemeral=True)
    gid, uid = str(i.guild.id), str(membre.id)
    bot.warnings.setdefault(gid, {}).setdefault(uid, []).append(
        {"r": raison, "by": str(i.user.id), "at": datetime.now(timezone.utc).isoformat()})
    count = len(bot.warnings[gid][uid])
    sanction = None
    if count == 3:
        try: await membre.timeout(datetime.now(timezone.utc)+timedelta(hours=1),reason="3 warns"); sanction="🔇 Mute 1h"
        except: pass
    elif count == 5:
        try: await membre.timeout(datetime.now(timezone.utc)+timedelta(hours=24),reason="5 warns"); sanction="🔇 Mute 24h"
        except: pass
    elif count >= 7:
        try: await membre.kick(reason="7 warns"); sanction="⚡ Kick"
        except: pass
    extra = f"**Total warns** `{count}`" + (f"\n**Sanction auto** {sanction}" if sanction else "")
    add_history(str(i.guild.id), str(membre.id), "warn", i.user.id, raison)
    await i.response.send_message(view=ModActionLayout("⚠️", "Avertissement", membre, raison, extra=extra, color=C.NEON_ORANGE))
    await log(i.guild, "Warn", f"**Membre :** {membre}\n**Raison :** {raison}\n**Par :** {i.user}", C.NEON_ORANGE)
    try: await membre.send(embed=emb(f"⚠️  Avertissement reçu",
        f"**Serveur :** {i.guild.name}\n**Raison :** {raison}\n**Total :** {count}", C.NEON_ORANGE))
    except: pass

@mod_group.command(name="unwarn", description="Retirer un avertissement")
@app_commands.describe(membre="Le membre")
@app_commands.default_permissions(moderate_members=True)
async def mod_unwarn(i: discord.Interaction, membre: discord.Member):
    # Vérification permission réelle
    if not i.user.guild_permissions.moderate_members:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Mettre en sourdine`."), ephemeral=True)
    gid, uid = str(i.guild.id), str(membre.id)
    lst = bot.warnings.get(gid, {}).get(uid, [])
    if not lst:
        return await i.response.send_message(embed=inf("Aucun warn"), ephemeral=True)
    lst.pop()
    await i.response.send_message(embed=ok("Warn retiré", f"{membre.mention} → **{len(lst)}** warn(s)."))

@mod_group.command(name="warns", description="Voir les avertissements")
@app_commands.describe(membre="Le membre (vide = toi)")
@app_commands.default_permissions(moderate_members=True)
async def mod_warns(i: discord.Interaction, membre: Optional[discord.Member]=None):
    # Vérification permission réelle
    if not i.user.guild_permissions.moderate_members:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Mettre en sourdine`."), ephemeral=True)
    m = membre or i.user
    lst = bot.warnings.get(str(i.guild.id), {}).get(str(m.id), [])
    if not lst:
        return await i.response.send_message(embed=inf("Aucun warn", f"{m.mention} est clean ✅"), ephemeral=True)
    e = emb(f"⚠️  Warns de {m.display_name}", f"**Total :** {len(lst)}", C.NEON_ORANGE)
    for idx, w in enumerate(lst[-10:], 1):
        raison = (w['r'][:200] + "…") if len(w['r']) > 200 else w['r']
        e.add_field(name=f"#{idx}", value=f"**Raison :** {raison}\n**Date :** {w['at'][:10]}", inline=True)
    await i.response.send_message(embed=e)

@mod_group.command(name="purge", description="Supprimer des messages")
@app_commands.describe(nombre="Nombre de messages (max 100)")
@app_commands.default_permissions(manage_messages=True)
async def mod_purge(i: discord.Interaction, nombre: int):
    # Vérification permission réelle
    if not i.user.guild_permissions.manage_messages:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Gérer les messages`."), ephemeral=True)
    if nombre <= 0:
        return await i.response.send_message(embed=er("Nombre invalide", "Indique un nombre entre 1 et 100."), ephemeral=True)
    await i.response.defer(ephemeral=True)
    deleted = await i.channel.purge(limit=min(nombre, 100))
    await i.followup.send(embed=ok("Purge", f"**{len(deleted)}** messages supprimés."))

@mod_group.command(name="rename", description="Renommer un membre")
@app_commands.describe(membre="Le membre", pseudo="Nouveau pseudo")
@app_commands.default_permissions(manage_nicknames=True)
async def mod_rename(i: discord.Interaction, membre: discord.Member, pseudo: str):
    # Vérification permission réelle
    if not i.user.guild_permissions.manage_nicknames:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Gérer les pseudos`."), ephemeral=True)
    old = membre.display_name
    try:
        await membre.edit(nick=pseudo)
        await i.response.send_message(embed=ok("Renommé", f"`{old}` → `{pseudo}`"))
    except discord.Forbidden:
        await i.response.send_message(embed=er("Permission manquante"), ephemeral=True)

@mod_group.command(name="lock", description="Verrouiller un salon")
@app_commands.describe(salon="Salon (vide = actuel)", lecture="Bloquer aussi la lecture")
@app_commands.default_permissions(manage_channels=True)
async def mod_lock(i: discord.Interaction, salon: Optional[discord.TextChannel]=None, lecture: bool=False):
    # Vérification permission réelle
    if not i.user.guild_permissions.manage_channels:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Gérer les salons`."), ephemeral=True)
    target = salon or i.channel
    await i.response.defer(ephemeral=True)
    try:
        overwrite = target.overwrites_for(i.guild.default_role)
        overwrite.update(send_messages=False)
        if lecture: overwrite.update(view_channel=False)
        await target.set_permissions(i.guild.default_role, overwrite=overwrite)
        await i.followup.send(embed=emb("🔒  Verrouillé", target.mention, C.NEON_RED))
    except discord.Forbidden:
        await i.followup.send(embed=er("Permission manquante"))

@mod_group.command(name="unlock", description="Déverrouiller un salon")
@app_commands.describe(salon="Salon (vide = actuel)")
@app_commands.default_permissions(manage_channels=True)
async def mod_unlock(i: discord.Interaction, salon: Optional[discord.TextChannel]=None):
    # Vérification permission réelle
    if not i.user.guild_permissions.manage_channels:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Gérer les salons`."), ephemeral=True)
    target = salon or i.channel
    await i.response.defer(ephemeral=True)
    try:
        overwrite = target.overwrites_for(i.guild.default_role)
        overwrite.update(send_messages=True, view_channel=True)
        await target.set_permissions(i.guild.default_role, overwrite=overwrite)
        await i.followup.send(embed=ok("🔓  Déverrouillé", target.mention))
    except discord.Forbidden:
        await i.followup.send(embed=er("Permission manquante"))

@mod_group.command(name="slowmode", description="Mode lent sur un salon")
@app_commands.describe(secondes="Délai en secondes (0 = désactiver)", salon="Salon cible (vide = actuel)")
@app_commands.default_permissions(manage_channels=True)
async def mod_slowmode(i: discord.Interaction, secondes: int, salon: Optional[discord.TextChannel]=None):
    # Vérification permission réelle
    if not i.user.guild_permissions.manage_channels:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Gérer les salons`."), ephemeral=True)
    target = salon or i.channel
    await i.response.defer(ephemeral=True)
    try:
        await target.edit(slowmode_delay=secondes)
        label = f"{secondes}s" if secondes > 0 else "Désactivé"
        await i.followup.send(embed=ok(f"Slowmode — {label}", f"Appliqué sur {target.mention}"))
    except discord.Forbidden:
        await i.followup.send(embed=er("Permission manquante"))

bot.tree.add_command(mod_group)

# ─── /music ─────────────────────────────────────────────────────────────
class MusicGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="music", description="♪ Musique")

music_group = MusicGroup()

@music_group.command(name="play", description="Jouer une musique depuis YouTube")
@app_commands.describe(recherche="Titre ou lien YouTube")
async def music_play(i: discord.Interaction, recherche: str):
    if not i.user.voice:
        return await i.response.send_message(embed=er("Pas dans un vocal"), ephemeral=True)
    vc_ch = i.user.voice.channel
    perms = vc_ch.permissions_for(i.guild.me)
    if not perms.connect or not perms.speak:
        return await i.response.send_message(embed=er("Permission manquante"), ephemeral=True)
    await i.response.defer()
    gid = str(i.guild.id)
    search_msg = await i.followup.send(embed=inf("♪  Recherche...", f"🔍 `{recherche}`"), wait=True)
    track = await fetch_track(recherche)
    if not track or not track.get('url'):
        await search_msg.edit(embed=er("Introuvable", "Aucun résultat. Essaie un autre titre."))
        return
    vc = bot.vc_pool.get(gid)
    if not vc or not vc.is_connected():
        try:
            vc = await vc_ch.connect()
            bot.vc_pool[gid] = vc
        except Exception as ex:
            await search_msg.edit(embed=er("Erreur vocal", str(ex)[:100]))
            return
    bot.queues.setdefault(gid, []).append(track)
    if not vc.is_playing() and not vc.is_paused():
        await next_track(gid)
        try: await search_msg.delete()
        except: pass
        await i.followup.send(view=MusicLayout(track, "▶ Lecture"))
    else:
        pos = len(bot.queues.get(gid, []))
        track["_pos"] = pos
        try: await search_msg.delete()
        except: pass
        await i.followup.send(view=MusicLayout(track, f"📋 Ajouté #{pos}"))

@music_group.command(name="pause", description="Mettre en pause")
async def music_pause(i: discord.Interaction):
    vc = bot.vc_pool.get(str(i.guild.id))
    if vc and vc.is_playing():
        vc.pause(); await i.response.send_message(embed=inf("♪  Pause"))
    else:
        await i.response.send_message(embed=er("Rien à mettre en pause"), ephemeral=True)

@music_group.command(name="resume", description="Reprendre la lecture")
async def music_resume(i: discord.Interaction):
    vc = bot.vc_pool.get(str(i.guild.id))
    if vc and vc.is_paused():
        vc.resume(); await i.response.send_message(embed=ok("♪  Lecture reprise"))
    else:
        await i.response.send_message(embed=er("Rien en pause"), ephemeral=True)

@music_group.command(name="skip", description="Passer à la suivante")
async def music_skip(i: discord.Interaction):
    vc = bot.vc_pool.get(str(i.guild.id))
    if vc and (vc.is_playing() or vc.is_paused()):
        vc.stop(); await i.response.send_message(embed=ok("⏭️  Skippé"))
    else:
        await i.response.send_message(embed=er("Rien à skipper"), ephemeral=True)

@music_group.command(name="stop", description="Arrêter et déconnecter")
async def music_stop(i: discord.Interaction):
    gid = str(i.guild.id); vc = bot.vc_pool.get(gid)
    if vc:
        bot.queues[gid] = []; bot.now_playing[gid] = None
        await vc.disconnect(); bot.vc_pool.pop(gid, None)
        await i.response.send_message(embed=ok("⏹️  Arrêté"))
    else:
        await i.response.send_message(embed=er("Bot pas dans un vocal"), ephemeral=True)

@music_group.command(name="queue", description="Voir la file musicale")
async def music_queue(i: discord.Interaction):
    gid = str(i.guild.id); q = bot.queues.get(gid, []); np = bot.now_playing.get(gid)
    if not np and not q:
        return await i.response.send_message(embed=inf("File vide"), ephemeral=True)
    desc = ""
    if np: desc += f"**▶ En cours :** {np['title']} `{fmt(np['duration'])}`\n\n"
    if q:
        desc += "**▸ File :**\n"
        for idx, t in enumerate(q[:10], 1): desc += f"`{idx}.` {t['title']} `{fmt(t['duration'])}`\n"
        if len(q) > 10: desc += f"*... et {len(q)-10} autre(s)*"
    await i.response.send_message(embed=emb("♪  File musicale", desc, C.NEON_CYAN))

@music_group.command(name="nowplaying", description="Musique en cours")
async def music_np(i: discord.Interaction):
    np = bot.now_playing.get(str(i.guild.id))
    if not np: return await i.response.send_message(embed=inf("Rien en cours"), ephemeral=True)
    await i.response.send_message(view=MusicLayout(np, "▶ En cours"))

@music_group.command(name="volume", description="Régler le volume (0-100)")
@app_commands.describe(niveau="Volume entre 0 et 100")
async def music_volume(i: discord.Interaction, niveau: int):
    vc = bot.vc_pool.get(str(i.guild.id))
    if not vc or not vc.is_playing():
        return await i.response.send_message(embed=er("Rien en cours"), ephemeral=True)
    n = max(0, min(100, niveau))
    if vc.source: vc.source.volume = n/100
    await i.response.send_message(embed=ok(f"Volume : {n}%"))

bot.tree.add_command(music_group)

# ─── /fun ───────────────────────────────────────────────────────────────
class FunGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="fun", description="▶ Divers & fun")

fun_group = FunGroup()

@fun_group.command(name="tirage", description="Tirage au sort")
@app_commands.describe(options="Options séparées par des virgules")
async def fun_tirage(i: discord.Interaction, options: str):
    choices = [o.strip() for o in options.split(",") if o.strip()]
    if len(choices) < 2:
        return await i.response.send_message(embed=er("Erreur", "Donne au moins 2 options."), ephemeral=True)
    winner = random.choice(choices)
    await i.response.send_message(embed=emb(
        f"◈  Tirage au sort",
        f"**Options :** {' ◈ '.join(choices)}\n\n► **Résultat : {winner}**", C.NEON_GOLD))

@fun_group.command(name="sondage_rapide", description="Sondage Oui/Non rapide")
@app_commands.describe(question="Ta question")
async def fun_sondage(i: discord.Interaction, question: str):
    e = emb(f"▸  Sondage rapide", f"**{question}**", C.NEON_CYAN)
    e.set_footer(text=f"Posé par {i.user.display_name}  ◈  AEGIS AI")
    await i.response.send_message(embed=e)
    msg = await i.original_response()
    await msg.add_reaction("👍"); await msg.add_reaction("👎"); await msg.add_reaction("🤷")

@fun_group.command(name="avatar", description="Voir l'avatar d'un membre")
@app_commands.describe(membre="Le membre (vide = toi)")
async def fun_avatar(i: discord.Interaction, membre: Optional[discord.Member]=None):
    m = membre or i.user
    await i.response.send_message(view=AvatarLayout(m))

@fun_group.command(name="dire", description="Faire parler le bot")
@app_commands.describe(message="Le message", salon="Salon cible (vide = actuel)")
@app_commands.default_permissions(manage_messages=True)
async def fun_dire(i: discord.Interaction, message: str, salon: Optional[discord.TextChannel]=None):
    target = salon or i.channel
    perms  = target.permissions_for(i.guild.me)
    if not perms.view_channel or not perms.send_messages:
        return await i.response.send_message(embed=er("Accès refusé"), ephemeral=True)
    await i.response.defer(ephemeral=True)
    await target.send(message)
    await i.followup.send(embed=ok("Envoyé", f"Dans {target.mention}"), ephemeral=True)

@fun_group.command(name="embed", description="Envoyer un embed personnalisé")
@app_commands.describe(titre="Titre", contenu="Contenu", couleur="Couleur hex (ex: #FF00FF)",
                        salon="Salon cible", image="URL image/GIF", miniature="URL miniature")
@app_commands.default_permissions(manage_messages=True)
async def fun_embed(i: discord.Interaction, titre: str, contenu: str,
                    couleur: str="#00FFFF", salon: Optional[discord.TextChannel]=None,
                    image: Optional[str]=None, miniature: Optional[str]=None):
    target = salon or i.channel
    perms  = target.permissions_for(i.guild.me)
    if not perms.view_channel or not perms.send_messages or not perms.embed_links:
        return await i.response.send_message(embed=er("Accès refusé"), ephemeral=True)
    try: color = int(couleur.replace("#",""), 16)
    except: color = C.NEON_CYAN
    await i.response.defer(ephemeral=True)
    e = discord.Embed(title=titre, description=contenu, color=color, timestamp=datetime.now(timezone.utc))
    e.set_footer(text=f"Par {i.user.display_name}  ◈  AEGIS AI")
    if image:
        if not any(image.lower().endswith(ext) for ext in ['.mp4','.mov','.webm','.avi']):
            try: e.set_image(url=image)
            except: pass
    if miniature: e.set_thumbnail(url=miniature)
    await target.send(embed=e)
    await i.followup.send(embed=ok("Envoyé !", f"Dans {target.mention}"), ephemeral=True)

@fun_group.command(name="dmall", description="Envoyer un DM à tous les membres")
@app_commands.describe(message="Le message à envoyer")
@app_commands.default_permissions(administrator=True)
async def fun_dmall(i: discord.Interaction, message: str):
    await i.response.defer(ephemeral=True)
    # fetch_members pour avoir TOUS les membres, pas juste le cache
    members = []
    try:
        async for m in i.guild.fetch_members(limit=None):
            if not m.bot:
                members.append(m)
    except Exception:
        members = [m for m in i.guild.members if not m.bot]
    total = len(members)
    if total == 0:
        return await i.followup.send(embed=er("Aucun membre trouvé",
            "Active **Server Members Intent** sur discord.com/developers → Bot → Privileged Gateway Intents."), ephemeral=True)
    await i.followup.send(embed=inf("📨  DM en cours...", f"Envoi à **{total}** membres..."), ephemeral=True)
    e_dm = discord.Embed(title=f"◈  Message de {i.guild.name}", description=message,
                         color=C.NEON_CYAN, timestamp=datetime.now(timezone.utc))
    e_dm.set_footer(text=f"Envoyé depuis {i.guild.name}  ◈  AEGIS AI")
    if i.guild.icon: e_dm.set_thumbnail(url=i.guild.icon.url)
    sent = failed = 0
    for m in members:
        try: await m.send(embed=e_dm); sent += 1
        except: failed += 1
        await asyncio.sleep(1.2)
    await i.edit_original_response(embed=ok("Terminé !",
        f"✅ Envoyés : {sent}\n❌ Échoués : {failed}\n📊 Total : {total}"))

bot.tree.add_command(fun_group)

# ─── /stats ─────────────────────────────────────────────────────────────
class StatsGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="stats", description="◆ XP & Statistiques")

stats_group = StatsGroup()

@stats_group.command(name="rank", description="Voir son niveau XP")
@app_commands.describe(membre="Le membre (vide = toi)")
async def stats_rank(i: discord.Interaction, membre: Optional[discord.Member]=None):
    m = membre or i.user; gid = str(i.guild.id); d = get_xp(gid, str(m.id))
    lv, xp = d["level"], d["xp"]; req = xp_req(lv+1)
    su = sorted(bot.xp_data.get(gid,{}).items(), key=lambda x:(x[1]["level"],x[1]["xp"]), reverse=True)
    rk = next((idx+1 for idx,(uid,_) in enumerate(su) if uid==str(m.id)), "?")
    await i.response.send_message(view=RankLayout(m, lv, xp, req, rk, d["messages"]))

@stats_group.command(name="top", description="Top 10 XP du serveur")
async def stats_top(i: discord.Interaction):
    gid = str(i.guild.id); gxp = bot.xp_data.get(gid, {})
    if not gxp:
        return await i.response.send_message(embed=inf("Classement vide"), ephemeral=True)
    su = sorted(gxp.items(), key=lambda x:(x[1]["level"],x[1]["xp"]), reverse=True)[:10]
    entries = []
    for uid, d in su:
        m = i.guild.get_member(int(uid))
        name = m.display_name if m else f"ID:{uid}"
        entries.append((name, d["level"], d["xp"]))
    await i.response.send_message(view=TopLayout(entries))

@stats_group.command(name="userinfo", description="Informations sur un membre")
@app_commands.describe(membre="Le membre (vide = toi)")
async def stats_userinfo(i: discord.Interaction, membre: Optional[discord.Member]=None):
    m = membre or i.user; gid = str(i.guild.id); d = get_xp(gid, str(m.id))
    await i.response.send_message(view=UserInfoLayout(m, d["level"], d["xp"]))

@stats_group.command(name="serverinfo", description="Informations sur le serveur")
async def stats_serverinfo(i: discord.Interaction):
    g = i.guild
    total = g.member_count or len(g.members) or 0
    bots  = sum(1 for m in g.members if m.bot)
    humans = max(0, total - bots)
    await i.response.send_message(view=ServerInfoLayout(g, humans, bots))

bot.tree.add_command(stats_group)

# ─── /server ────────────────────────────────────────────────────────────
class ServerGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="server", description="⚙️ Configuration du serveur")

server_group = ServerGroup()

@server_group.command(name="setup", description="Setup complet du serveur")
@app_commands.describe(style="Style du serveur")
@app_commands.choices(style=[
    app_commands.Choice(name="🌐 Communauté",  value="communaute"),
    app_commands.Choice(name="🎮 Gaming",      value="gaming"),
    app_commands.Choice(name="🎭 Jeu de Rôle", value="rp"),
    app_commands.Choice(name="📚 Éducation",   value="education"),
    app_commands.Choice(name="🎌 Anime/Manga", value="anime")])
@app_commands.default_permissions(administrator=True)
async def server_setup(i: discord.Interaction, style: str="communaute"):
    # Vérification permission réelle
    if not i.user.guild_permissions.administrator:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Administrateur`."), ephemeral=True)
    await i.response.defer()
    g = i.guild; cfg = SETUPS[style]; created = {"roles":0,"text":0,"voice":0}
    for name, color in cfg["roles"]:
        if not discord.utils.get(g.roles, name=name):
            try: await g.create_role(name=name,color=discord.Color(color)); created["roles"]+=1; await asyncio.sleep(0.4)
            except: pass
    for cat_name, (texts, voices) in cfg["struct"].items():
        cat = discord.utils.get(g.categories, name=cat_name)
        if not cat:
            try:
                ow = {g.default_role:discord.PermissionOverwrite(view_channel=False)} if "STAFF" in cat_name or "MJ" in cat_name else {}
                cat = await g.create_category(cat_name, overwrites=ow); await asyncio.sleep(0.4)
            except: continue
        for cn in texts:
            if not discord.utils.get(g.text_channels, name=cn):
                try: await g.create_text_channel(cn,category=cat); created["text"]+=1; await asyncio.sleep(0.4)
                except: pass
        for vn in voices:
            if not discord.utils.get(g.voice_channels, name=vn):
                try: await g.create_voice_channel(vn,category=cat); created["voice"]+=1; await asyncio.sleep(0.4)
                except: pass
    for ln in ["📊・logs","logs"]:
        lc = discord.utils.get(g.text_channels, name=ln)
        if lc: bot.logs_ch[str(g.id)] = lc.id; break
    e = ok(f"Setup terminé — {cfg['label']}")
    e.add_field(name="Rôles créés",  value=f"**{created['roles']}**",  inline=True)
    e.add_field(name="Salons texte", value=f"**{created['text']}**",   inline=True)
    e.add_field(name="Salons vocal", value=f"**{created['voice']}**",  inline=True)
    e.add_field(name="Étapes suivantes",
                value="`/server arrivee` `/server depart` `/server panel` `/server verification`", inline=False)
    await i.followup.send(embed=e)

@server_group.command(name="arrivee", description="Configurer le salon des messages de bienvenue")
@app_commands.describe(salon_id="ID du salon")
@app_commands.default_permissions(administrator=True)
async def server_arrivee(i: discord.Interaction, salon_id: str):
    # Vérification permission réelle
    if not i.user.guild_permissions.administrator:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Administrateur`."), ephemeral=True)
    clean = salon_id.strip().replace("<#","").replace(">","").strip()
    try:
        cid = int(clean)
        ch  = i.guild.get_channel(cid) or await i.guild.fetch_channel(cid)
        if not ch: raise ValueError()
        bot.arrivee[str(i.guild.id)] = ch.id
        await i.response.send_message(embed=ok("Arrivées configurées", f"Salon : {ch.mention}"))
    except:
        await i.response.send_message(embed=er("ID invalide",
            "Active le **Mode développeur** puis clic droit sur le salon → Copier l'identifiant."), ephemeral=True)

@server_group.command(name="depart", description="Configurer le salon des messages de départ")
@app_commands.describe(salon_id="ID du salon")
@app_commands.default_permissions(administrator=True)
async def server_depart(i: discord.Interaction, salon_id: str):
    # Vérification permission réelle
    if not i.user.guild_permissions.administrator:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Administrateur`."), ephemeral=True)
    clean = salon_id.strip().replace("<#","").replace(">","").strip()
    try:
        cid = int(clean)
        ch  = i.guild.get_channel(cid) or await i.guild.fetch_channel(cid)
        if not ch: raise ValueError()
        bot.depart_ch[str(i.guild.id)] = ch.id
        await i.response.send_message(embed=ok("Départs configurés", f"Salon : {ch.mention}"))
    except:
        await i.response.send_message(embed=er("ID invalide"), ephemeral=True)

@server_group.command(name="panel", description="Créer un panel de tickets")
@app_commands.describe(titre="Titre", description="Description", role_support="Rôle support", image="URL image/GIF")
@app_commands.default_permissions(administrator=True)
async def server_panel(i: discord.Interaction, titre: str="Support",
                        description: str="Clique pour ouvrir un ticket.",
                        role_support: Optional[discord.Role]=None,
                        image: Optional[str]=None):
    # Vérification permission réelle
    if not i.user.guild_permissions.administrator:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Administrateur`."), ephemeral=True)
    bot.ticket_cfg[str(i.guild.id)] = {"sr": role_support.id if role_support else None}
    if not check_perms(i.channel, i.guild.me):
        return await i.response.send_message(embed=er("Accès refusé"), ephemeral=True)
    await i.response.defer(ephemeral=True)
    e = emb(f"🎫  {titre}", description, C.NEON_CYAN)
    if image:
        if not any(image.lower().endswith(ext) for ext in ['.mp4','.mov','.webm','.avi']):
            try: e.set_image(url=image)
            except: pass
    await i.channel.send(embed=e, view=TicketView())
    await i.followup.send(embed=ok("Panel créé !"), ephemeral=True)

@server_group.command(name="reglement", description="Envoyer le règlement")
@app_commands.describe(type_reglement="Type", avec_bouton="Ajouter bouton d'acceptation", role="Rôle à l'acceptation")
@app_commands.choices(type_reglement=[
    app_commands.Choice(name="Défaut", value="def"),
    app_commands.Choice(name="Personnalisé", value="custom")])
@app_commands.default_permissions(administrator=True)
async def server_reglement(i: discord.Interaction, type_reglement: str="def",
                            avec_bouton: bool=True, role: Optional[discord.Role]=None):
    # Vérification permission réelle
    if not i.user.guild_permissions.administrator:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Administrateur`."), ephemeral=True)
    if type_reglement == "custom":
        return await i.response.send_modal(ReglModal(avec_bouton, role))
    if role: bot.verif_roles[str(i.guild.id)] = role.id
    if not check_perms(i.channel, i.guild.me):
        return await i.response.send_message(embed=er("Accès refusé"), ephemeral=True)
    rules = [
        ("◈  Respect",    "Respecte tous les membres et le staff."),
        ("◈  Anti-spam",  "Évite de répéter les mêmes messages."),
        ("◈  Publicité",  "Toute publicité non autorisée est interdite."),
        ("◈  Contenu",    "Aucun contenu NSFW, violent ou illégal."),
        ("◈  Staff",      "Les décisions du staff sont définitives."),
    ]
    e = discord.Embed(title="◈  Règlement", description="─────────────────────",
                      color=C.NEON_CYAN, timestamp=datetime.now(timezone.utc))
    for t, c in rules: e.add_field(name=t, value=c, inline=False)
    await i.response.defer(ephemeral=True)
    await i.channel.send(embed=e, view=RulesView() if avec_bouton else None)
    await i.followup.send(embed=ok("Règlement envoyé !"), ephemeral=True)

@server_group.command(name="verification", description="Créer un panel de vérification")
@app_commands.describe(role="Rôle à donner", titre="Titre", description="Description")
@app_commands.default_permissions(administrator=True)
async def server_verification(i: discord.Interaction, role: Optional[discord.Role]=None,
                               titre: str="Vérification", description: str="Clique pour te vérifier !"):
    # Vérification permission réelle
    if not i.user.guild_permissions.administrator:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Administrateur`."), ephemeral=True)
    gid = str(i.guild.id)
    if not role:
        role = discord.utils.get(i.guild.roles, name="✅ Vérifié")
        if not role:
            try: role = await i.guild.create_role(name="✅ Vérifié", color=discord.Color(C.NEON_GREEN))
            except:
                return await i.response.send_message(embed=er("Erreur"), ephemeral=True)
    bot.verif_roles[gid] = role.id
    if not check_perms(i.channel, i.guild.me):
        return await i.response.send_message(embed=er("Accès refusé"), ephemeral=True)
    e = emb(f"◈  {titre}", f"{description}\n\n**Rôle :** {role.mention}", C.NEON_CYAN)
    await i.response.defer(ephemeral=True)
    await i.channel.send(embed=e, view=VerifyView())
    await i.followup.send(embed=ok("Panel créé !"), ephemeral=True)

@server_group.command(name="verification_quiz", description="Vérification par code aléatoire")
@app_commands.describe(role="Rôle attribué", titre="Titre", description="Description", nb_faux="Nombre de faux codes")
@app_commands.choices(nb_faux=[
    app_commands.Choice(name="2 faux codes (3 total)", value=2),
    app_commands.Choice(name="3 faux codes (4 total)", value=3)])
@app_commands.default_permissions(administrator=True)
async def server_verif_quiz(i: discord.Interaction, role: discord.Role,
                             titre: str="◈  Vérification",
                             description: str="Sélectionne le bon code pour accéder au serveur.",
                             nb_faux: int=3):
    # Vérification permission réelle
    if not i.user.guild_permissions.administrator:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Administrateur`."), ephemeral=True)
    gid = str(i.guild.id)
    if not check_perms(i.channel, i.guild.me):
        return await i.response.send_message(embed=er("Accès refusé"), ephemeral=True)
    await i.response.defer(ephemeral=True)
    true_code  = gen_code()
    fake_codes = [gen_code() for _ in range(nb_faux)]
    all_codes  = [true_code] + fake_codes
    random.shuffle(all_codes)
    # Sauvegarder true_code + all_codes + role_id pour restauration après redéploiement
    bot.verif_quiz[gid] = {
        "true_code": true_code,
        "role_id": role.id,
        "all_codes": all_codes  # nécessaire pour recréer la vue après redémarrage
    }
    _save_data()
    options = [
        discord.SelectOption(label=f"Code Numéro {idx+1}", description=code_val, value=code_val)
        for idx, code_val in enumerate(all_codes)
    ]
    bar = "─" * 8
    e = discord.Embed(title=titre, description=description, color=C.NEON_CYAN, timestamp=datetime.now(timezone.utc))
    e.add_field(name="\u200b", value=f"```\n{bar}  {true_code}  {bar}\n```", inline=False)
    e.set_footer(text="AEGIS AI  ◈  Choisis le bon code dans le menu ci-dessous")
    # Utiliser la vue globale persistante (survit aux redéploiements)
    await i.channel.send(embed=e, view=VerifQuizView(gid))
    await i.followup.send(embed=ok("Vérification créée !", f"Bon code : `{true_code}`\nRôle : {role.mention}"), ephemeral=True)

@server_group.command(name="backup", description="Sauvegarder la structure du serveur")
@app_commands.describe(nom="Nom de la sauvegarde")
@app_commands.default_permissions(administrator=True)
async def server_backup(i: discord.Interaction, nom: Optional[str]=None):
    # Vérification permission réelle
    if not i.user.guild_permissions.administrator:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Administrateur`."), ephemeral=True)
    await i.response.defer(ephemeral=True)
    g = i.guild
    name = nom or f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    roles  = [r for r in g.roles if r.name != "@everyone" and not r.managed]
    texts  = list(g.text_channels); voices = list(g.voice_channels); cats = list(g.categories)
    data = {
        "roles":  [{"name":r.name,"color":r.color.value} for r in roles],
        "cats":   [{"name":c.name} for c in cats],
        "text":   [{"name":c.name,"cat":c.category.name if c.category else None} for c in texts],
        "voice":  [{"name":c.name,"cat":c.category.name if c.category else None} for c in voices],
    }
    bot.backups.setdefault(str(g.id), {})[name] = data
    await i.followup.send(embed=ok("Sauvegarde créée",
        f"**{name}**\nRôles : {len(data['roles'])} | Salons : {len(data['text'])+len(data['voice'])}"),
        ephemeral=True)

@server_group.command(name="restore", description="Restaurer une sauvegarde")
@app_commands.describe(nom="Nom (vide = voir la liste)")
@app_commands.default_permissions(administrator=True)
async def server_restore(i: discord.Interaction, nom: Optional[str]=None):
    # Vérification permission réelle
    if not i.user.guild_permissions.administrator:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Administrateur`."), ephemeral=True)
    await i.response.defer(ephemeral=True)
    gid = str(i.guild.id); saves = bot.backups.get(gid, {})
    if not nom or not nom.strip():
        if not saves:
            return await i.followup.send(embed=er("Aucune sauvegarde"), ephemeral=True)
        desc = ""
        for idx,(name,data) in enumerate(sorted(saves.items(),reverse=True)[:20],1):
            nr = len(data.get("roles",[])); nt = len(data.get("text",[])); nv = len(data.get("voice",[]))
            desc += f"`{idx}.` **{name}** — {nr} roles | {nt} texte | {nv} vocal\n"
        return await i.followup.send(embed=inf(f"Sauvegardes ({len(saves)})", desc), ephemeral=True)
    data = saves.get(nom)
    if not data:
        return await i.followup.send(embed=er("Introuvable"), ephemeral=True)
    r = {"roles":0,"channels":0}
    for x in data.get("roles",[]):
        if not discord.utils.get(i.guild.roles, name=x["name"]):
            try: await i.guild.create_role(name=x["name"],color=discord.Color(x.get("color",0))); r["roles"]+=1; await asyncio.sleep(0.3)
            except: pass
    for x in data.get("cats",[]):
        if not discord.utils.get(i.guild.categories, name=x["name"]):
            try: await i.guild.create_category(x["name"]); await asyncio.sleep(0.3)
            except: pass
    for x in data.get("text",[]):
        if not discord.utils.get(i.guild.text_channels, name=x["name"]):
            try:
                cat = discord.utils.get(i.guild.categories, name=x.get("cat"))
                await i.guild.create_text_channel(x["name"],category=cat); r["channels"]+=1; await asyncio.sleep(0.3)
            except: pass
    await i.followup.send(embed=ok("Restauré !", f"Rôles : **{r['roles']}** | Salons : **{r['channels']}**"))

@server_group.command(name="autorole", description="Rôle automatique pour les nouveaux membres")
@app_commands.describe(action="Ajouter ou retirer", role="Le rôle", reset="Supprimer tous")
@app_commands.choices(action=[
    app_commands.Choice(name="Ajouter", value="add"),
    app_commands.Choice(name="Retirer", value="rem")])
@app_commands.default_permissions(administrator=True)
async def server_autorole(i: discord.Interaction, action: str="add",
                           role: Optional[discord.Role]=None, reset: bool=False):
    # Vérification permission réelle
    if not i.user.guild_permissions.administrator:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Administrateur`."), ephemeral=True)
    gid = str(i.guild.id)
    current = bot.auto_roles.get(gid, [])
    if isinstance(current, int): current = [current]
    if reset:
        bot.auto_roles[gid] = []
        return await i.response.send_message(embed=ok("Auto-rôles supprimés"))
    if not role:
        if not current:
            return await i.response.send_message(embed=inf("Aucun auto-rôle"), ephemeral=True)
        names = [i.guild.get_role(rid) for rid in current]
        desc  = "\n".join([f"◈ {r.mention}" for r in names if r]) or "Aucun"
        return await i.response.send_message(embed=inf(f"Auto-rôles ({len(current)})", desc), ephemeral=True)
    if action == "add":
        if role.id not in current:
            current.append(role.id); bot.auto_roles[gid] = current
            await i.response.send_message(embed=ok("Auto-rôle ajouté", f"{role.mention}"))
        else:
            await i.response.send_message(embed=inf("Déjà présent"), ephemeral=True)
    else:
        if role.id in current:
            current.remove(role.id); bot.auto_roles[gid] = current
            await i.response.send_message(embed=ok("Auto-rôle retiré", f"{role.mention}"))
        else:
            await i.response.send_message(embed=inf("Pas trouvé"), ephemeral=True)

@server_group.command(name="rolemenu", description="Créer un menu de sélection de rôles")
@app_commands.describe(titre="Titre du menu", roles="Mentions des rôles")
@app_commands.default_permissions(administrator=True)
async def server_rolemenu(i: discord.Interaction, titre: str, roles: str):
    # Vérification permission réelle
    if not i.user.guild_permissions.administrator:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Administrateur`."), ephemeral=True)
    ids = re.findall(r'<@&(\d+)>', roles) or re.findall(r'\b(\d{17,20})\b', roles)
    objs = [i.guild.get_role(int(x)) for x in ids if i.guild.get_role(int(x))]
    if not objs:
        for word in roles.split():
            word = word.strip().lstrip('@')
            r = discord.utils.get(i.guild.roles, name=word)
            if r and r not in objs: objs.append(r)
    if not objs:
        return await i.response.send_message(embed=er("Aucun rôle trouvé"), ephemeral=True)
    e = emb(f"◉  {titre}", "\n".join([f"◈ {r.mention}" for r in objs]), C.NEON_PINK)
    if not check_perms(i.channel, i.guild.me):
        return await i.response.send_message(embed=er("Accès refusé"), ephemeral=True)
    await i.response.defer(ephemeral=True)
    # Sauvegarder les IDs de rôles pour pouvoir restaurer la vue au redémarrage
    bot.rolemenu_cfg.setdefault(str(i.guild.id), [])
    bot.rolemenu_cfg[str(i.guild.id)] = [r.id for r in objs]
    _save_data()
    await i.channel.send(embed=e, view=RoleMenuView(objs, i.guild.id))
    await i.followup.send(embed=ok("Menu créé !"), ephemeral=True)

@server_group.command(name="tempvoice", description="Salons vocaux temporaires")
@app_commands.describe(salon="Salon déclencheur")
@app_commands.default_permissions(administrator=True)
async def server_tempvoice(i: discord.Interaction, salon: discord.VoiceChannel):
    # Vérification permission réelle
    if not i.user.guild_permissions.administrator:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Administrateur`."), ephemeral=True)
    bot.temp_voices[str(i.guild.id)] = salon.id
    await i.response.send_message(embed=ok("Vocaux temporaires",
        f"Rejoins **{salon.name}** pour créer ton salon automatiquement !"))

@server_group.command(name="antiraid", description="Configurer l'anti-raid")
@app_commands.describe(activer="Activer", seuil="Joins par 10s", action="kick ou ban")
@app_commands.default_permissions(administrator=True)
async def server_antiraid(i: discord.Interaction, activer: bool=True, seuil: int=5, action: str="kick"):
    # Vérification permission réelle
    if not i.user.guild_permissions.administrator:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Administrateur`."), ephemeral=True)
    bot.raid_cfg[str(i.guild.id)] = {"enabled":activer,"threshold":seuil,"action":action}
    await i.response.send_message(embed=emb("◈  Anti-Raid",
        f"**Statut :** {'✅ Activé' if activer else '❌ Désactivé'}\n**Seuil :** {seuil}/10s\n**Action :** {action}", C.NEON_PINK))

@server_group.command(name="antispam", description="Configurer l'anti-spam")
@app_commands.describe(activer="Activer", messages="Max messages", fenetre="Fenêtre secondes",
                        mentions="Max mentions", action="mute/kick/ban", duree_mute="Durée mute (min)")
@app_commands.default_permissions(administrator=True)
async def server_antispam(i: discord.Interaction, activer: bool=True, messages: int=5,
                           fenetre: int=5, mentions: int=5, action: str="mute", duree_mute: int=5):
    # Vérification permission réelle
    if not i.user.guild_permissions.administrator:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Administrateur`."), ephemeral=True)
    bot.spam_cfg[str(i.guild.id)] = {"enabled":activer,"limit":messages,"window":fenetre,
                                      "mentions":mentions,"action":action,"dur":duree_mute}
    await i.response.send_message(embed=emb("◈  Anti-Spam",
        f"**Statut :** {'✅ Activé' if activer else '❌ Désactivé'}\n**Messages :** {messages}/{fenetre}s\n**Action :** {action}", C.NEON_PINK))

@server_group.command(name="antinuke", description="Protection anti-nuke")
@app_commands.describe(activer="Activer", seuil="Actions max/10s", action="kick ou ban",
                        whitelist_add="ID à whitelister", whitelist_rem="ID à retirer")
@app_commands.default_permissions(administrator=True)
async def server_antinuke(i: discord.Interaction, activer: bool=True, seuil: int=5,
                           action: str="kick", whitelist_add: Optional[str]=None,
                           whitelist_rem: Optional[str]=None):
    # Vérification permission réelle
    if not i.user.guild_permissions.administrator:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Administrateur`."), ephemeral=True)
    gid = str(i.guild.id)
    cfg = bot.nuke_cfg.setdefault(gid, default_nuke_cfg())
    cfg.update({"enabled":activer,"threshold":max(1,seuil),
                "action":action if action in("kick","ban") else "kick"})
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
        f"**Statut :** {'✅ Activé' if activer else '❌ Désactivé'}\n**Seuil :** {seuil}/10s\n"
        f"**Sanction :** {cfg['action']}\n**Whitelist :** {wl_txt}", C.NEON_RED))

@server_group.command(name="suggestion", description="Envoyer une suggestion")
@app_commands.describe(texte="Ta suggestion", salon="Salon suggestions")
async def server_suggestion(i: discord.Interaction, texte: str, salon: Optional[discord.TextChannel]=None):
    # Vérification permission réelle
    if not i.user.guild_permissions.manage_messages:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Gérer les messages`."), ephemeral=True)
    if not salon:
        for n in ["💡・suggestions","suggestions","suggest"]:
            salon = discord.utils.get(i.guild.text_channels, name=n)
            if salon: break
    if not salon:
        return await i.response.send_message(embed=er("Salon introuvable"), ephemeral=True)
    texte_safe = (texte[:3500] + "…") if len(texte) > 3500 else texte
    e = emb("💡  Suggestion", texte_safe, C.NEON_GOLD)
    e.add_field(name="Par", value=i.user.mention, inline=True)
    e.add_field(name="Statut", value="⏳ En attente", inline=True)
    e.set_thumbnail(url=i.user.display_avatar.url)
    await i.response.defer(ephemeral=True)
    msg = await salon.send(embed=e, view=SuggView())
    await msg.add_reaction("👍"); await msg.add_reaction("👎")
    await i.followup.send(embed=ok("Suggestion envoyée !"), ephemeral=True)

@server_group.command(name="creersalon", description="Créer un salon texte")
@app_commands.describe(nom="Nom du salon", categorie="Catégorie (optionnel)")
@app_commands.default_permissions(manage_channels=True)
async def server_creersalon(i: discord.Interaction, nom: str, categorie: Optional[discord.CategoryChannel]=None):
    # Vérification permission réelle
    if not i.user.guild_permissions.manage_channels:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Gérer les salons`."), ephemeral=True)
    try:
        ch = await i.guild.create_text_channel(nom, category=categorie)
        await i.response.send_message(embed=ok("Salon créé", ch.mention))
    except discord.Forbidden:
        await i.response.send_message(embed=er("Permission manquante"), ephemeral=True)

@server_group.command(name="creervoice", description="Créer un salon vocal")
@app_commands.describe(nom="Nom du salon", categorie="Catégorie (optionnel)")
@app_commands.default_permissions(manage_channels=True)
async def server_creervoice(i: discord.Interaction, nom: str, categorie: Optional[discord.CategoryChannel]=None):
    # Vérification permission réelle
    if not i.user.guild_permissions.manage_channels:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Gérer les salons`."), ephemeral=True)
    try:
        ch = await i.guild.create_voice_channel(nom, category=categorie)
        await i.response.send_message(embed=ok("Vocal créé", f"🔊 {ch.name}"))
    except discord.Forbidden:
        await i.response.send_message(embed=er("Permission manquante"), ephemeral=True)

@server_group.command(name="supprimersalon", description="Supprimer un salon")
@app_commands.describe(salon="Le salon à supprimer")
@app_commands.default_permissions(manage_channels=True)
async def server_supprimersalon(i: discord.Interaction, salon: discord.TextChannel):
    # Vérification permission réelle
    if not i.user.guild_permissions.manage_channels:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Gérer les salons`."), ephemeral=True)
    name = salon.name
    try:
        await salon.delete()
        await i.response.send_message(embed=ok("Supprimé", f"`{name}`"))
    except discord.Forbidden:
        await i.response.send_message(embed=er("Permission manquante"), ephemeral=True)

@server_group.command(name="creerole", description="Créer un rôle")
@app_commands.describe(nom="Nom du rôle", couleur="Couleur hex (ex: #FF00FF)")
@app_commands.default_permissions(manage_roles=True)
async def server_creerole(i: discord.Interaction, nom: str, couleur: str="#00FFFF"):
    # Vérification permission réelle
    if not i.user.guild_permissions.manage_roles:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Gérer les rôles`."), ephemeral=True)
    try:
        color = discord.Color(int(couleur.replace("#",""), 16))
        role = await i.guild.create_role(name=nom, color=color)
        await i.response.send_message(embed=ok("Rôle créé", role.mention))
    except discord.Forbidden:
        await i.response.send_message(embed=er("Permission manquante"), ephemeral=True)

@server_group.command(name="addrole", description="Ajouter un rôle à un membre")
@app_commands.describe(membre="Le membre", role="Le rôle")
@app_commands.default_permissions(manage_roles=True)
async def server_addrole(i: discord.Interaction, membre: discord.Member, role: discord.Role):
    # Vérification RÉELLE côté code — default_permissions seul ne suffit pas
    if not i.user.guild_permissions.manage_roles:
        return await i.response.send_message(embed=er("Permission refusée", "Tu n'as pas la permission `Gérer les rôles`."), ephemeral=True)
    # Empêcher d'attribuer un rôle plus haut que soi
    if role >= i.user.top_role and i.user.id != i.guild.owner_id:
        return await i.response.send_message(embed=er("Impossible", "Tu ne peux pas attribuer un rôle supérieur ou égal au tien."), ephemeral=True)
    try:
        await membre.add_roles(role)
        await i.response.send_message(embed=ok("Rôle ajouté", f"{role.mention} → {membre.mention}"))
    except discord.Forbidden:
        await i.response.send_message(embed=er("Permission manquante"), ephemeral=True)

@server_group.command(name="removerole", description="Retirer un rôle d'un membre")
@app_commands.describe(membre="Le membre", role="Le rôle")
@app_commands.default_permissions(manage_roles=True)
async def server_removerole(i: discord.Interaction, membre: discord.Member, role: discord.Role):
    if not i.user.guild_permissions.manage_roles:
        return await i.response.send_message(embed=er("Permission refusée", "Tu n'as pas la permission `Gérer les rôles`."), ephemeral=True)
    if role >= i.user.top_role and i.user.id != i.guild.owner_id:
        return await i.response.send_message(embed=er("Impossible", "Tu ne peux pas retirer un rôle supérieur ou égal au tien."), ephemeral=True)
    try:
        await membre.remove_roles(role)
        await i.response.send_message(embed=inf("Rôle retiré", f"{role.mention} retiré de {membre.mention}"))
    except discord.Forbidden:
        await i.response.send_message(embed=er("Permission manquante"), ephemeral=True)

@server_group.command(name="roleall", description="Donner un rôle à tous les membres")
@app_commands.describe(role="Le rôle")
@app_commands.default_permissions(administrator=True)
async def server_roleall(i: discord.Interaction, role: discord.Role):
    # Vérification permission réelle
    if not i.user.guild_permissions.administrator:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Administrateur`."), ephemeral=True)
    await i.response.defer()
    count = 0
    for m in i.guild.members:
        if not m.bot and role not in m.roles:
            try: await m.add_roles(role); count += 1; await asyncio.sleep(0.5)
            except: pass
    await i.followup.send(embed=ok("Rôle donné à tous", f"{role.mention} — **{count}** membres"))

bot.tree.add_command(server_group)

# ─── /events ────────────────────────────────────────────────────────────
class EventsGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="events", description="🎉 Événements — Giveaways & Sondages")

events_group = EventsGroup()

@events_group.command(name="giveaway", description="Créer un giveaway")
@app_commands.describe(titre="Titre", prix="Prix", duree="Durée (ex: 10m, 2h, 1j)", gagnants="Nb gagnants")
@app_commands.default_permissions(administrator=True)
async def events_giveaway(i: discord.Interaction, titre: str, prix: str, duree: str, gagnants: int=1):
    perms = i.channel.permissions_for(i.guild.me)
    if not perms.view_channel or not perms.send_messages or not perms.embed_links:
        return await i.response.send_message(embed=er("Accès refusé"), ephemeral=True)
    try:
        duree_lower = duree.strip().lower()
        if duree_lower.endswith('j'):   total_s = int(duree_lower[:-1]) * 86400
        elif duree_lower.endswith('h'): total_s = int(duree_lower[:-1]) * 3600
        elif duree_lower.endswith('m'): total_s = int(duree_lower[:-1]) * 60
        elif duree_lower.endswith('s'): total_s = int(duree_lower[:-1])
        else:                           total_s = int(duree_lower) * 60
        if total_s < 10: total_s = 10
    except:
        return await i.response.send_message(embed=er("Durée invalide","Exemples : `10m` `2h` `1j`"), ephemeral=True)
    await i.response.defer()
    end = datetime.now(timezone.utc) + timedelta(seconds=total_s)
    titre_safe = (titre[:200] + "…") if len(titre) > 200 else titre
    prix_safe  = (prix[:200] + "…") if len(prix) > 200 else prix
    e = discord.Embed(title=f"🎉  {titre_safe.upper()}",
                      description=f"◎ **Prix :** {prix_safe}\n─────────────────────",
                      color=C.NEON_GOLD, timestamp=datetime.now(timezone.utc))
    e.add_field(name="◈ Gagnants",    value=f"**{gagnants}**",               inline=True)
    e.add_field(name="◎ Participants", value=f"**0**",                        inline=True)
    e.add_field(name="⏰ Fin",         value=f"<t:{int(end.timestamp())}:R>", inline=True)
    e.set_footer(text=f"Organisé par {i.user.display_name}  ◈  AEGIS AI")
    msg = await i.channel.send(embed=e)
    mid = str(msg.id)
    bot.giveaways[mid] = {"title":titre_safe,"prize":prix_safe,"winners":gagnants,"end":end.isoformat(),
                          "cid":str(i.channel.id),"gid":str(i.guild.id),"p":[],"ended":False}
    v = GAView(mid); bot.add_view(v); await msg.edit(view=v)
    await i.followup.send(embed=ok("Giveaway créé !"), ephemeral=True)

@events_group.command(name="reroll", description="Relancer un giveaway terminé")
@app_commands.describe(message_id="ID du message du giveaway")
@app_commands.default_permissions(administrator=True)
async def events_reroll(i: discord.Interaction, message_id: str):
    g = bot.giveaways.get(message_id)
    if not g:              return await i.response.send_message(embed=er("Introuvable"), ephemeral=True)
    if not g.get("ended"): return await i.response.send_message(embed=er("Encore en cours"), ephemeral=True)
    p = g.get("p", [])
    if not p:              return await i.response.send_message(embed=er("Aucun participant"), ephemeral=True)
    await i.response.defer()
    picks = random.sample(p, min(g.get("winners", 1), len(p)))
    results = await asyncio.gather(*[bot.fetch_user(wid) for wid in picks], return_exceptions=True)
    winners = [w for w in results if not isinstance(w, Exception)]
    if winners:
        mentions = ", ".join([w.mention for w in winners])
        await i.followup.send(
            content=" ".join([w.mention for w in winners]),
            embed=emb("🎉  Reroll !",
                f"**Gagnant(s) :** {mentions}\n**Prix :** {g.get('prize')}", C.NEON_GOLD))
    else:
        await i.followup.send(embed=er("Erreur reroll", "Impossible de récupérer les gagnants."), ephemeral=True)

@events_group.command(name="poll", description="Créer un sondage interactif")
@app_commands.describe(question="La question", option1="Option 1", option2="Option 2",
                        option3="Option 3", option4="Option 4", option5="Option 5",
                        duree="Durée en minutes (0 = sans limite)")
@app_commands.default_permissions(manage_messages=True)
async def events_poll(i: discord.Interaction, question: str, option1: str, option2: str,
                       option3: Optional[str]=None, option4: Optional[str]=None,
                       option5: Optional[str]=None, duree: int=0):
    opts = [o for o in [option1,option2,option3,option4,option5] if o]
    end  = None
    if duree > 0: end = datetime.now(timezone.utc) + timedelta(minutes=duree)
    desc = f"**{question[:300]}**\n\n"
    for idx, o in enumerate(opts):
        o_safe = (o[:200] + "…") if len(o) > 200 else o
        desc += f"{PE[idx]} **{o_safe}**\n`░░░░░░░░░░` 0 vote (0%)\n\n"
    desc += f"▸ **0 vote au total**"
    if end: desc += f"\n\n⏰ Fin : <t:{int(end.timestamp())}:R>"
    if len(desc) > 4000: desc = desc[:3990] + "…"
    e = emb(f"▸  Sondage", desc, C.NEON_CYAN)
    e.set_footer(text=f"Par {i.user.display_name}" + (f" ◈ {duree} min" if duree > 0 else "") + "  ◈  AEGIS AI")
    await i.response.send_message(embed=e)
    msg = await i.original_response(); mid = str(msg.id)
    poll_data = {"q":question,"opts":opts,"v":{},"ended":False,
                 "gid":str(i.guild.id),"cid":str(i.channel.id)}
    if end: poll_data["end"] = end.isoformat()
    bot.polls[mid] = poll_data
    await msg.edit(view=PollView(mid, opts))

bot.tree.add_command(events_group)

# ══════════════════════════════════════════════
#  COMMANDES RACINE
# ══════════════════════════════════════════════
@bot.tree.command(name="aide", description="Liste de toutes les commandes AEGIS AI")
async def aide(i: discord.Interaction):
    await i.response.send_message(view=AideLayout())

@bot.tree.command(name="ping", description="Latence du bot")
async def ping(i: discord.Interaction):
    await i.response.send_message(embed=inf("Pong !", f"⚡ `{round(bot.latency*1000)} ms`"))

# ══════════════════════════════════════════════
#  /admin_panel — Panel Owner avec pagination
# ══════════════════════════════════════════════
class AdminPanelView(discord.ui.View):
    def __init__(self, owner_id: int, guilds: list, stats: dict):
        super().__init__(timeout=300)
        self.owner_id = owner_id
        self.guilds = guilds
        self.stats = stats
        self.page = 0
        self.per_page = 10

    @property
    def total_pages(self) -> int:
        return max(1, (len(self.guilds) + self.per_page - 1) // self.per_page)

    def build_embed(self) -> discord.Embed:
        g_count = len(self.guilds)
        e = discord.Embed(
            title="☢️  AEGIS AI — Panel Admin Owner",
            color=C.AEGIS_PINK,
            timestamp=datetime.now(timezone.utc),
        )
        e.set_thumbnail(url=bot.user.display_avatar.url)
        e.set_footer(text=f"AEGIS AI  ◈  Owner Only  ◈  Page {self.page+1}/{self.total_pages}")
        e.add_field(
            name="◈  Stats globales",
            value=(f"**Serveurs :** `{g_count}`\n"
                   f"**Humains :** `{self.stats['humans']}`\n"
                   f"**Latence :** `{round(bot.latency*1000)} ms`"),
            inline=True)
        e.add_field(
            name="🛡️  Protections",
            value=(f"**Anti-nuke :** `{self.stats['nuke']}`\n"
                   f"**Anti-spam :** `{self.stats['spam']}`\n"
                   f"**Anti-raid :** `{self.stats['raid']}`"),
            inline=True)
        e.add_field(
            name="📊  Activité",
            value=(f"**Joueurs XP :** `{self.stats['xp']}`\n"
                   f"**Giveaways :** `{self.stats['ga']}`\n"
                   f"**Sondages :** `{len(bot.polls)}`"),
            inline=True)
        start = self.page * self.per_page
        end = min(start + self.per_page, g_count)
        lines = []
        total_len = 0
        truncated = 0
        for idx, g in enumerate(self.guilds[start:end], start=start+1):
            # Tronque le nom du serveur pour éviter les lignes trop longues
            gname = (g.name[:40] + "…") if len(g.name) > 40 else g.name
            line = f"`{idx:>3}.` **{gname}** — `{g.member_count or 0}` mbr  `{g.id}`"
            # Discord embed field limit = 1024 chars (on garde 60 de marge)
            if total_len + len(line) + 1 > 960:
                truncated = (end - start) - len(lines)
                break
            lines.append(line)
            total_len += len(line) + 1
        value = "\n".join(lines) if lines else "*Aucun serveur*"
        if truncated > 0:
            value += f"\n*… +{truncated} autre(s) — page suivante*"
        if len(value) > 1024:
            value = value[:1020] + "…"
        e.add_field(
            name=f"📋  Serveurs ({g_count})",
            value=value,
            inline=False)
        invite = f"https://discord.com/oauth2/authorize?client_id={bot.application_id}&permissions=8&integration_type=0&scope=bot"
        liens_value = f"[Dev Portal](https://discord.com/developers/applications) • [Support](https://discord.gg/6rN8pneGdy) • [Inviter]({invite})"
        if len(liens_value) > 1024:
            liens_value = liens_value[:1020] + "…"
        e.add_field(
            name="🔗  Liens",
            value=liens_value,
            inline=False)
        return e

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Accès refusé.", ephemeral=True)
            return False
        return True

    def _refresh_buttons(self):
        self.prev_btn.disabled = (self.page == 0)
        self.next_btn.disabled = (self.page >= self.total_pages - 1)

    @discord.ui.button(label="◀ Précédent", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
        self._refresh_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Suivant ▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.total_pages - 1:
            self.page += 1
        self._refresh_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="🔄 Rafraîchir", style=discord.ButtonStyle.primary)
    async def refresh_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.guilds = sorted(bot.guilds, key=lambda x: x.member_count or 0, reverse=True)
        self.stats = _compute_admin_stats()
        if self.page >= self.total_pages:
            self.page = self.total_pages - 1
        self._refresh_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


def _compute_admin_stats() -> dict:
    guilds = bot.guilds
    total_users = sum(g.member_count or 0 for g in guilds)
    return {
        "humans": max(0, total_users - len(guilds)),
        "nuke":   sum(1 for c in bot.nuke_cfg.values() if c.get("enabled")),
        "spam":   sum(1 for c in bot.spam_cfg.values() if c.get("enabled")),
        "raid":   sum(1 for c in bot.raid_cfg.values() if c.get("enabled")),
        "xp":     sum(len(v) for v in bot.xp_data.values()),
        "ga":     sum(1 for g in bot.giveaways.values() if not g.get("ended")),
    }


@bot.tree.command(name="admin_panel", description="Panel d'administration [Owner uniquement]")
async def admin_panel(i: discord.Interaction):
    if BOT_OWNER_ID == 0:
        return await i.response.send_message(embed=er("BOT_OWNER_ID manquant"), ephemeral=True)
    if i.user.id != BOT_OWNER_ID:
        return await i.response.send_message(embed=er("Accès refusé", "Réservé au propriétaire."), ephemeral=True)
    guilds = sorted(bot.guilds, key=lambda x: x.member_count or 0, reverse=True)
    view = AdminPanelView(BOT_OWNER_ID, guilds, _compute_admin_stats())
    view._refresh_buttons()
    await i.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)


# ══════════════════════════════════════════════
#  /owner_dmall_ultime — DM ALL members ALL servers (Owner only)
# ══════════════════════════════════════════════
class DMAllUltimateConfirm(discord.ui.View):
    def __init__(self, owner_id: int, message: str, targets: list):
        super().__init__(timeout=60)
        self.owner_id = owner_id
        self.message = message
        self.targets = targets
        self.confirmed = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Accès refusé.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="✅ Confirmer & envoyer", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        for c in self.children:
            c.disabled = True
        await interaction.response.edit_message(
            embed=inf("📨  DM Ultime en cours…", f"Envoi à **{len(self.targets)}** membres.\nÇa peut prendre un moment."),
            view=self,
        )
        self.stop()

    @discord.ui.button(label="✖ Annuler", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for c in self.children:
            c.disabled = True
        await interaction.response.edit_message(embed=warn("Annulé", "Aucun DM envoyé."), view=self)
        self.stop()


@bot.tree.command(name="owner_dmall_ultime", description="[OWNER] DM à tous les membres de tous les serveurs")
@app_commands.describe(message="Le message à envoyer en DM à tous")
async def owner_dmall_ultime(i: discord.Interaction, message: str):
    if BOT_OWNER_ID == 0 or i.user.id != BOT_OWNER_ID:
        return await i.response.send_message(embed=er("Accès refusé", "Réservé au propriétaire."), ephemeral=True)
    seen = set()
    targets = []
    for g in bot.guilds:
        # fetch_members force le chargement complet même si le cache est partiel
        try:
            async for m in g.fetch_members(limit=None):
                if m.bot or m.id == BOT_OWNER_ID or m.id in seen:
                    continue
                seen.add(m.id)
                targets.append(m)
        except Exception:
            for m in g.members:
                if m.bot or m.id == BOT_OWNER_ID or m.id in seen:
                    continue
                seen.add(m.id)
                targets.append(m)
    if not targets:
        return await i.response.send_message(embed=er("Aucun membre trouvé"), ephemeral=True)
    preview = discord.Embed(
        title="⚠️  DM Ultime — Confirmation requise",
        description=(f"Tu es sur le point d'envoyer un DM à **{len(targets)}** membres uniques "
                     f"répartis sur **{len(bot.guilds)}** serveurs.\n\n"
                     f"**Message :**\n> {message[:500]}\n\n"
                     f"⏱  Rate-limit : 1.5s/DM → durée estimée ≈ **{round(len(targets)*1.5/60)} min**\n"
                     f"🛑  Auto-stop activé si >30 % d'échecs d'affilée (protection anti-ban)."),
        color=C.NEON_RED,
    )
    preview.set_footer(text="⚠️  Usage massif = risque de ban Discord. Utilise avec raison valable.")
    view = DMAllUltimateConfirm(BOT_OWNER_ID, message, targets)
    await i.response.send_message(embed=preview, view=view, ephemeral=True)
    await view.wait()
    if not view.confirmed:
        return
    e_dm = discord.Embed(
        title="◈  Message de AEGIS AI",
        description=message,
        color=C.AEGIS_PINK,
        timestamp=datetime.now(timezone.utc),
    )
    e_dm.set_footer(text="AEGIS AI  ◈  Message du propriétaire")
    if bot.user.display_avatar:
        e_dm.set_thumbnail(url=bot.user.display_avatar.url)
    sent = failed = 0
    recent_window = []
    stopped_reason = None
    idx = 0
    for idx, m in enumerate(targets, 1):
        try:
            await m.send(embed=e_dm)
            sent += 1
            recent_window.append(True)
        except Exception:
            failed += 1
            recent_window.append(False)
        if len(recent_window) > 20:
            recent_window.pop(0)
        if len(recent_window) >= 20:
            fail_rate = recent_window.count(False) / len(recent_window)
            if fail_rate > 0.30:
                stopped_reason = f"Trop d'échecs consécutifs ({int(fail_rate*100)} %). Stoppé pour protéger le bot."
                break
        # Mise à jour progression toutes les 25 personnes (sans bloquer la boucle)
        if idx % 25 == 0:
            try:
                await i.followup.send(
                    embed=inf("📨  DM Ultime en cours…",
                              f"Progression : **{idx}/{len(targets)}**\n"
                              f"✅ Envoyés : `{sent}`  •  ❌ Échoués : `{failed}`"),
                    ephemeral=True
                )
            except Exception:
                pass
        await asyncio.sleep(1.5)
    final = ok("DM Ultime terminé",
               f"✅ Envoyés : **{sent}**\n❌ Échoués : **{failed}**\n📊 Total : **{len(targets)}**")
    if stopped_reason:
        final = warn("DM Ultime arrêté",
                     f"{stopped_reason}\n\n✅ Envoyés : **{sent}**\n❌ Échoués : **{failed}**\n📊 Total traités : **{idx}/{len(targets)}**")
    try:
        await i.edit_original_response(embed=final, view=None)
    except Exception:
        await i.followup.send(embed=final, ephemeral=True)

# ══════════════════════════════════════════════
#  NOUVEAUTÉS — /server antinuke pause, /mod tempban, /mod historique,
#               /ai resume, /server logs_filter, /fun ia_image,
#               /events bingo, /events trivia, /music lyrics
# ══════════════════════════════════════════════

# ─── Anti-nuke pause ────────────────────────────
@server_group.command(name="antinuke_pause", description="Pause temporaire de l'anti-nuke")
@app_commands.describe(minutes="Durée de la pause en minutes (0 = annuler)")
@app_commands.default_permissions(administrator=True)
async def server_antinuke_pause(i: discord.Interaction, minutes: int = 30):
    # Vérification permission réelle
    if not i.user.guild_permissions.administrator:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Administrateur`."), ephemeral=True)
    gid = str(i.guild.id)
    if minutes <= 0:
        bot.nuke_paused_until.pop(gid, None)
        return await i.response.send_message(embed=ok("Anti-nuke réactivé"))
    end = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    bot.nuke_paused_until[gid] = end.isoformat()
    await i.response.send_message(embed=warn(
        "Anti-nuke en pause",
        f"Réactivation auto : <t:{int(end.timestamp())}:R>\nUtilise `/server antinuke_pause minutes:0` pour annuler."))

# ─── Logs filter (toggle types) ─────────────────
LOG_TYPES = ["ban", "kick", "mute", "warn", "unban", "purge", "tempban", "antinuke", "antiraid", "antispam"]

@server_group.command(name="logs_filter", description="Choisir quels types d'événements logger")
@app_commands.describe(types="Liste séparée par virgules (ex: ban,kick,mute) — 'all' pour tout, 'reset' pour défaut")
@app_commands.default_permissions(administrator=True)
async def server_logs_filter(i: discord.Interaction, types: str = "all"):
    # Vérification permission réelle
    if not i.user.guild_permissions.administrator:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Administrateur`."), ephemeral=True)
    gid = str(i.guild.id)
    t = types.strip().lower()
    if t == "all":
        bot.logs_filters[gid] = LOG_TYPES.copy()
    elif t == "reset":
        bot.logs_filters.pop(gid, None)
    else:
        chosen = [x.strip() for x in t.split(",") if x.strip() in LOG_TYPES]
        if not chosen:
            return await i.response.send_message(embed=er("Types invalides",
                f"Choisis parmi : {', '.join(LOG_TYPES)}"), ephemeral=True)
        bot.logs_filters[gid] = chosen
    actuels = bot.logs_filters.get(gid, LOG_TYPES)
    await i.response.send_message(embed=ok("Filtre logs", f"Actifs : `{', '.join(actuels)}`"))

# ─── /mod tempban ───────────────────────────────
@mod_group.command(name="tempban", description="Bannir temporairement un membre")
@app_commands.describe(membre="Le membre", duree="Durée (ex: 10m, 2h, 7j)", raison="Raison")
@app_commands.default_permissions(ban_members=True)
async def mod_tempban(i: discord.Interaction, membre: discord.Member, duree: str, raison: str = "Aucune"):
    # Vérification permission réelle
    if not i.user.guild_permissions.ban_members:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Bannir des membres`."), ephemeral=True)
    if not can_target(i.user, membre):
        return await i.response.send_message(embed=er("Impossible"), ephemeral=True)
    try:
        d = duree.strip().lower()
        if   d.endswith('j'): secs = int(d[:-1]) * 86400
        elif d.endswith('h'): secs = int(d[:-1]) * 3600
        elif d.endswith('m'): secs = int(d[:-1]) * 60
        else: secs = int(d) * 60
        if secs < 60: secs = 60
    except:
        return await i.response.send_message(embed=er("Durée invalide", "Ex: `10m` `2h` `7j`"), ephemeral=True)
    end = datetime.now(timezone.utc) + timedelta(seconds=secs)
    try:
        await membre.ban(reason=f"Tempban: {raison} — fin {end.isoformat()}")
        bot.tempbans.setdefault(str(i.guild.id), {})[str(membre.id)] = end.isoformat()
        add_history(str(i.guild.id), str(membre.id), "tempban", i.user.id, raison)
        await i.response.send_message(view=ModActionLayout(
            "⏳", "Tempban", membre, raison,
            extra=f"**Fin :** <t:{int(end.timestamp())}:R>", color=C.NEON_RED))
        await log(i.guild, "Tempban", f"**Membre :** {membre}\n**Durée :** {duree}\n**Par :** {i.user}", C.NEON_RED)
    except discord.Forbidden:
        await i.response.send_message(embed=er("Permission manquante"), ephemeral=True)

# ─── /mod historique ────────────────────────────
@mod_group.command(name="historique", description="Voir l'historique de modération d'un membre")
@app_commands.describe(membre="Le membre")
@app_commands.default_permissions(moderate_members=True)
async def mod_historique(i: discord.Interaction, membre: discord.Member):
    # Vérification permission réelle
    if not i.user.guild_permissions.moderate_members:
        return await i.response.send_message(
            embed=er("Permission refusée", "Tu n'as pas la permission `Mettre en sourdine`."), ephemeral=True)
    hist = bot.mod_history.get(str(i.guild.id), {}).get(str(membre.id), [])
    if not hist:
        return await i.response.send_message(embed=inf("Historique vide", f"{membre.mention} est clean ✅"), ephemeral=True)
    e = emb(f"📋  Historique — {membre.display_name}", f"**Total :** {len(hist)} action(s)", C.NEON_ORANGE)
    icons = {"warn":"⚠️","mute":"🔇","kick":"⚡","ban":"⛔","tempban":"⏳","unban":"♻️"}
    desc = ""
    for entry in hist[-15:][::-1]:
        ic = icons.get(entry.get("type"), "◈")
        date = entry.get("at", "")[:10]
        reason = (entry.get("reason","")[:80] + "…") if len(entry.get("reason","")) > 80 else entry.get("reason","")
        desc += f"{ic} **{entry.get('type','?').upper()}** · `{date}` · {reason}\n"
    if len(desc) > 4000: desc = desc[:3990] + "…"
    e.description = f"**Total :** {len(hist)} action(s)\n\n{desc}"
    await i.response.send_message(embed=e, ephemeral=True)

# ─── /ai resume ─────────────────────────────────
@ai_group.command(name="resume", description="Résumer les derniers messages du salon avec l'IA")
@app_commands.describe(nombre="Nombre de messages à résumer (10-100)")
async def ai_resume(i: discord.Interaction, nombre: int = 50):
    nombre = max(10, min(100, nombre))
    await i.response.defer()
    msgs = []
    async for m in i.channel.history(limit=nombre):
        if m.author.bot or not m.content.strip(): continue
        msgs.append(f"{m.author.display_name}: {m.content[:200]}")
    if not msgs:
        return await i.followup.send(embed=inf("Rien à résumer", "Aucun message texte récent."), ephemeral=True)
    msgs.reverse()
    convo = "\n".join(msgs)[:4000]
    system_resume = (
        "Tu es AEGIS AI. Résume cette conversation Discord en 4-6 lignes max. "
        "Style GLaDOS sarcastique mais utile. Capte les sujets principaux. Français."
    )
    rep = await ask_groq(f"Voici les derniers messages :\n{convo}\n\nFais un résumé court et capté.", system=system_resume)
    await i.followup.send(view=AIChatLayout(f"Résumé des {len(msgs)} derniers messages", rep, i.user))

# ─── /fun ia_image ──────────────────────────────
@fun_group.command(name="ia_image", description="Générer une image avec l'IA (Pollinations, gratuit)")
@app_commands.describe(prompt="Description de l'image")
async def fun_ia_image(i: discord.Interaction, prompt: str):
    await i.response.defer()
    seed = random.randint(1, 999999)
    safe_prompt = re.sub(r'[^\w\s,.-]', '', prompt)[:200]
    url = f"https://image.pollinations.ai/prompt/{safe_prompt.replace(' ', '%20')}?seed={seed}&nologo=true&width=1024&height=1024"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=45)) as s:
            async with s.get(url) as r:
                if r.status != 200:
                    return await i.followup.send(embed=er("Erreur génération", f"Code {r.status}"), ephemeral=True)
                data = await r.read()
        f = discord.File(fp=__import__('io').BytesIO(data), filename="aegis.png")
        e = emb("◈  Image IA générée", f"**Prompt :** {prompt[:300]}", C.NEON_PINK)
        e.set_image(url="attachment://aegis.png")
        e.set_footer(text=f"Demandé par {i.user.display_name}  ◈  Pollinations  ◈  AEGIS AI")
        await i.followup.send(embed=e, file=f)
    except Exception as e:
        await i.followup.send(embed=er("Erreur", f"`{str(e)[:120]}`"), ephemeral=True)

# ─── /events bingo ──────────────────────────────
@events_group.command(name="bingo", description="Lancer un mini-bingo dans le salon (1-75)")
@app_commands.describe(intervalle="Délai entre tirages en secondes (5-60)")
@app_commands.default_permissions(manage_messages=True)
async def events_bingo(i: discord.Interaction, intervalle: int = 15):
    cid = str(i.channel.id)
    if cid in bot.bingo_active:
        return await i.response.send_message(embed=er("Bingo déjà en cours", "Attends qu'il se termine."), ephemeral=True)
    intervalle = max(5, min(60, intervalle))
    nums = list(range(1, 76)); random.shuffle(nums)
    bot.bingo_active[cid] = {"numbers": nums, "drawn": []}
    await i.response.send_message(embed=emb("🎱  BINGO !",
        f"Le tirage commence dans **3s** !\nUn nombre est tiré toutes les **{intervalle}s** parmi 1-75.\n"
        f"Premier à compléter sa carte gagne ! 🏆", C.NEON_GOLD))
    await asyncio.sleep(3)
    drawn = []
    while bot.bingo_active.get(cid) and bot.bingo_active[cid]["numbers"] and len(drawn) < 75:
        n = bot.bingo_active[cid]["numbers"].pop(0)
        drawn.append(n); bot.bingo_active[cid]["drawn"] = drawn
        try:
            await i.channel.send(embed=emb(f"🎱  Bingo — Tirage #{len(drawn)}",
                f"### **{n}**\n\nNombres déjà sortis : `{', '.join(map(str, drawn[-15:]))}`", C.NEON_PINK))
        except: pass
        await asyncio.sleep(intervalle)
    bot.bingo_active.pop(cid, None)

@events_group.command(name="bingo_stop", description="Arrêter le bingo en cours")
@app_commands.default_permissions(manage_messages=True)
async def events_bingo_stop(i: discord.Interaction):
    cid = str(i.channel.id)
    if cid in bot.bingo_active:
        bot.bingo_active.pop(cid, None)
        await i.response.send_message(embed=ok("Bingo arrêté"))
    else:
        await i.response.send_message(embed=inf("Aucun bingo en cours"), ephemeral=True)

# ─── /events trivia ─────────────────────────────
@events_group.command(name="trivia", description="Quiz de culture générale (Open Trivia DB)")
@app_commands.describe(categorie="Catégorie (vide = aléatoire)")
@app_commands.choices(categorie=[
    app_commands.Choice(name="🎲 Aléatoire", value="0"),
    app_commands.Choice(name="🎮 Jeux vidéo", value="15"),
    app_commands.Choice(name="🎬 Films", value="11"),
    app_commands.Choice(name="🎵 Musique", value="12"),
    app_commands.Choice(name="🌍 Géographie", value="22"),
    app_commands.Choice(name="📚 Histoire", value="23"),
    app_commands.Choice(name="🔬 Science", value="17"),
])
async def events_trivia(i: discord.Interaction, categorie: str = "0"):
    cid = str(i.channel.id)
    if cid in bot.trivia_active:
        return await i.response.send_message(embed=er("Trivia déjà en cours"), ephemeral=True)
    await i.response.defer()
    cat_param = f"&category={categorie}" if categorie != "0" else ""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get(f"https://opentdb.com/api.php?amount=1&type=multiple{cat_param}") as r:
                data = await r.json()
        if not data.get("results"):
            return await i.followup.send(embed=er("API indisponible"), ephemeral=True)
        q = data["results"][0]
        import html
        question = html.unescape(q["question"])
        correct  = html.unescape(q["correct_answer"])
        all_ans  = [html.unescape(a) for a in q["incorrect_answers"]] + [correct]
        random.shuffle(all_ans)
        end = datetime.now(timezone.utc) + timedelta(seconds=30)
        bot.trivia_active[cid] = {"answer": correct, "asker": i.user.id}
        letters = ["🅰️","🅱️","🅲","🅳"]
        desc = f"**{question}**\n\n" + "\n".join([f"{letters[idx]} {a}" for idx, a in enumerate(all_ans)])
        desc += f"\n\n⏰ Tu as **30 secondes** ! Réponds dans le chat.\n*Catégorie : {q.get('category','?')} · Difficulté : {q.get('difficulty','?')}*"
        msg = await i.followup.send(embed=emb("🧠  Trivia !", desc, C.NEON_PINK))
        def check(m):
            return m.channel.id == int(cid) and not m.author.bot \
                   and m.content.lower().strip() == correct.lower().strip()
        try:
            winner_msg = await bot.wait_for("message", timeout=30.0, check=check)
            await i.channel.send(embed=emb("🏆  Bonne réponse !",
                f"{winner_msg.author.mention} a trouvé : **{correct}**", C.NEON_GREEN))
        except asyncio.TimeoutError:
            await i.channel.send(embed=emb("⏰  Temps écoulé",
                f"Personne n'a trouvé. La réponse était : **{correct}**", C.NEON_ORANGE))
        finally:
            bot.trivia_active.pop(cid, None)
    except Exception as e:
        bot.trivia_active.pop(cid, None)
        await i.followup.send(embed=er("Erreur", f"`{str(e)[:100]}`"), ephemeral=True)

# ─── /music lyrics ──────────────────────────────
@music_group.command(name="lyrics", description="Paroles de la musique en cours (lyrics.ovh)")
@app_commands.describe(recherche="Format: artiste - titre (vide = musique en cours)")
async def music_lyrics(i: discord.Interaction, recherche: Optional[str] = None):
    await i.response.defer()
    if not recherche:
        np = bot.now_playing.get(str(i.guild.id))
        if not np: return await i.followup.send(embed=er("Rien en cours", "Indique `artiste - titre`"), ephemeral=True)
        recherche = np.get("title", "")
    if "-" in recherche:
        artist, title = [x.strip() for x in recherche.split("-", 1)]
    else:
        artist, title = "", recherche.strip()
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            url = f"https://api.lyrics.ovh/v1/{aiohttp.helpers.quote(artist)}/{aiohttp.helpers.quote(title)}"
            async with s.get(url) as r:
                data = await r.json()
        lyrics = data.get("lyrics", "").strip()
        if not lyrics:
            return await i.followup.send(embed=er("Paroles introuvables",
                "Essaie le format `artiste - titre` plus précis."), ephemeral=True)
        if len(lyrics) > 3800: lyrics = lyrics[:3790] + "…"
        e = emb(f"♪  {title}", f"**Artiste :** {artist or '?'}\n\n{lyrics}", C.NEON_CYAN)
        e.set_footer(text="Source : lyrics.ovh  ◈  AEGIS AI")
        await i.followup.send(embed=e)
    except Exception as e:
        await i.followup.send(embed=er("Erreur", f"`{str(e)[:100]}`"), ephemeral=True)

# ─── Hooks pour ajouter à l'historique sur ban/kick/warn/mute ───
# (on étend les commandes existantes via un wrapper d'event)
@bot.event
async def on_member_ban(guild, user):
    try:
        await asyncio.sleep(0.5)
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
            if entry.target.id == user.id:
                add_history(str(guild.id), str(user.id), "ban", entry.user.id, entry.reason or "Aucune")
                await nuke_check(guild, entry.user.id, "ban"); break
    except: pass


# ══════════════════════════════════════════════
#  RUN
# ══════════════════════════════════════════════
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    token = os.environ.get('DISCORD_BOT_TOKEN')
    if token:
        logger.info("⚡ AEGIS AI démarre...")
        bot.run(token)
    else:
        logger.error("❌ DISCORD_BOT_TOKEN manquant dans Railway → Variables !")
