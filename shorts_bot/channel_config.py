"""Central settings for the Lantern Lore Shorts bot.

Everything a channel owner might want to tweak lives here.
"""

CHANNEL_NAME = "Lantern Lore"
CHANNEL_TAGLINE = "Legends whispered in the dark."

# ---------------------------------------------------------------- voice
# Kokoro voices: bm_george / bm_lewis (British male), am_michael / am_onyx (US male)
KOKORO_VOICE = "bm_george"
KOKORO_LANG = "en-gb"          # "en-gb" for bm_/bf_ voices, "en-us" for am_/af_ voices
VOICE_SPEED = 0.95
# Fallback voice if Kokoro fails (Microsoft Edge online voices, free)
EDGE_TTS_VOICE = "en-GB-RyanNeural"
PAUSE_BETWEEN_SCENES = 0.45     # seconds; pauses inside a scene come naturally from the voice

# ---------------------------------------------------------------- length
MIN_WORDS = 115
MAX_WORDS = 140
MAX_DURATION_SECONDS = 58.5     # Shorts target: 15-60 s
MIN_DURATION_SECONDS = 42.0     # shorter narration is rewritten longer
MAX_SPEEDUP = 1.12              # audio may be sped up at most by this factor to fit

# ---------------------------------------------------------------- upload
YOUTUBE_CATEGORY_ID = "24"      # Entertainment
PRIVACY_STATUS = "public"
DECLARE_SYNTHETIC_MEDIA = True  # AI narration -> honest disclosure
DEFAULT_SHORTS_PER_DAY = 3      # can be overridden with repo variable SHORTS_PER_DAY

BASE_HASHTAGS = ["#shorts", "#legends", "#folklore", "#scarystories", "#unexplained"]

# ---------------------------------------------------------------- content series
# weight = how often the series is chosen relative to the others.
# fiction = True means the story is an original invented tale (no fact-check pass).
SERIES = [
    {
        "key": "appalachian",
        "label": "APPALACHIAN LEGENDS",
        "weight": 3,
        "fiction": False,
        "brief": (
            "Folklore, reported sightings, ghost stories and old-time superstitions from the "
            "Appalachian Mountains (West Virginia, Kentucky, Tennessee, the Carolinas, Virginia, "
            "Pennsylvania, north Georgia). Examples of the kind of subject: Mothman, the Brown "
            "Mountain Lights, the Bell Witch, the Flatwoods Monster, the Grafton Monster, "
            "the Snarly Yow, Sheepsquatch, haint blue porches, 'don't whistle in the woods'."
        ),
        "hashtags": ["#appalachia", "#appalachianfolklore"],
    },
    {
        "key": "cryptids",
        "label": "CRYPTID FILES",
        "weight": 2,
        "fiction": False,
        "brief": "Cryptids and strange creature sightings from anywhere in the world, as told in local accounts.",
        "hashtags": ["#cryptids", "#cryptid"],
    },
    {
        "key": "haunted_places",
        "label": "HAUNTED PLACES",
        "weight": 2,
        "fiction": False,
        "brief": "Real places around the world (houses, lighthouses, roads, forests, ships, hotels) with famous ghost legends.",
        "hashtags": ["#haunted", "#ghoststories"],
    },
    {
        "key": "unexplained_history",
        "label": "UNEXPLAINED HISTORY",
        "weight": 2,
        "fiction": False,
        "brief": (
            "Historical mysteries and strange events that happened at least 50 years ago and were never "
            "fully explained (vanished ships, lost colonies, strange lights, odd phenomena). "
            "No recent crimes and no cases involving living private individuals."
        ),
        "hashtags": ["#history", "#mystery"],
    },
    {
        "key": "world_folklore",
        "label": "FOLKLORE OF THE WORLD",
        "weight": 2,
        "fiction": False,
        "brief": "Spooky legends, spirits and folk creatures from countries and cultures around the world.",
        "hashtags": ["#mythology", "#worldfolklore"],
    },
    {
        "key": "old_superstitions",
        "label": "OLD SUPERSTITIONS",
        "weight": 1,
        "fiction": False,
        "brief": "Old superstitions, folk customs and warnings, and the eerie stories people told about why they exist.",
        "hashtags": ["#superstition", "#oldwivestales"],
    },
    {
        "key": "campfire_tales",
        "label": "CAMPFIRE TALES",
        "weight": 1,
        "fiction": True,
        "brief": (
            "An ORIGINAL short horror story invented by you, told in first person like a story at a "
            "campfire. Settings: deep woods, mountain cabins, back roads, small towns, night shifts. "
            "Must end with an unsettling twist."
        ),
        "hashtags": ["#horrorstory", "#campfirestories"],
    },
]

# Generic footage searches used when a scene-specific search finds nothing
FALLBACK_FOOTAGE_QUERIES = [
    "dark forest night", "fog forest", "misty mountains", "abandoned house",
    "night sky stars", "candle flame dark", "old road night", "moon clouds night",
]
