"""Writes the narration script (and fact-checks real legends)."""

import re

from . import channel_config as cfg
from .llm_gemini_client import generate_json

SYSTEM = f"""You are the head writer and narrator of "{cfg.CHANNEL_NAME}", a YouTube Shorts channel
that retells legends, folklore and unexplained stories in a calm, eerie, campfire storyteller voice.
Style: vivid but plain spoken English that flows naturally when read aloud: mix short and medium-length
sentences, connect thoughts with "and", "but", "until"; avoid chains of tiny fragments ("Silence. Then nothing. Cold.").
Storyteller voice,
no profanity, no gore, suspense over shock. Every short opens with a hook in the first sentence
and ends with a chilling final line and a short question to the viewer. Never use emojis. Spell out numbers as words."""


def word_count(text):
    return len(re.findall(r"[A-Za-z0-9']+", text))


def full_narration(script):
    return " ".join(s["narration"].strip() for s in script["scenes"])


HOOK_RULES = """HOOK (most important part - viewers swipe away within two seconds):
- The very first sentence has at most twelve words and drops the viewer straight into the strangest,
  most unsettling moment or claim of the story. No slow scene-setting, no dates or "In the year ..." openings,
  no "Have you ever heard of ...".
- Good hook patterns: a disturbing detail ("Every dog in Kecksburg started howling at the same minute."),
  a warning ("If you hear your name in these woods, don't answer."), a contradiction
  ("The footprints went straight up a wall - and kept going.").
- Then keep tension rising; reveal the most eerie detail near the end."""


def _script_prompt(series, topic, feedback="", performance_hint=""):
    if series["fiction"]:
        truth_rules = (
            "This is an ORIGINAL fictional story. It must not copy any existing story. "
            "It is fine to tell it as if it happened to the narrator."
        )
    else:
        truth_rules = (
            "This is a REAL legend or mystery. Only state facts you are confident are part of the real "
            "legend or record. Present supernatural claims as legend, never as proven fact "
            "(use phrases like 'locals say', 'according to the legend', 'witnesses claimed'). "
            "Do not invent names, dates or numbers. If unsure about a detail, leave it out or keep it vague."
        )
    return f"""Write one YouTube Short script.
Series: {series['label']} - {series['brief']}
Subject: {topic['subject']}
Angle: {topic['angle']}
Region: {topic['region']}

{truth_rules}

Length: {cfg.MIN_WORDS}-{cfg.MAX_WORDS} words of narration in total (about 48-57 seconds spoken).
Count your words - drafts under {cfg.MIN_WORDS} words are rejected.
Structure: 4 to 6 scenes. Scene 1 = hook.
{HOOK_RULES}
Ending: the last scene ends with an eerie closing line, followed by ONE short question to the viewer
(max ten words) that invites a comment, e.g. "Would you have opened the door?" or "Have you ever seen these lights?".
Never ask for likes or subscriptions.
{performance_hint}
For every scene give THREE stock-footage search queries (each 2-4 plain English words describing a filmable,
atmospheric shot, e.g. "foggy forest night", "old wooden cabin", "lantern in dark"), from most specific to most
general. Think about what a stock video site really has: landscapes, weather, buildings, objects, light. No people's faces,
no brand names, no monsters (stock sites have none) - use mood shots instead.
The footage MUST fit the story's setting: same kind of landscape and country, same season and time of day
(e.g. a winter story in an English village -> "snowy village night", "frozen field dawn", never a summer
river or an Asian temple). Avoid objects that clearly belong to another culture or era.
{feedback}
Return JSON exactly like:
{{"title": "curiosity-driven but honest title, max 60 characters, no hashtags, no emojis, no clickbait lies",
 "scenes": [{{"narration": "...", "footage_queries": ["specific", "medium", "general"]}}],
 "description": "2 short sentences for the YouTube description",
 "tags": ["8 to 12 lowercase tags"]}}"""


def _fact_check(script, topic):
    prompt = f"""You are a careful fact-checker for a folklore channel. Subject: {topic['subject']}.
Check this narration for: invented names/dates/numbers, claims presented as proven fact that are only
legend, confusion with a different legend, statements about living private people, offensive stereotypes.
Fix problems with minimal changes, keep the same scene count, tone and similar length.

Script JSON:
{script}

Return JSON: {{"problems_found": ["..."], "scenes": [{{"narration": "...", "footage_queries": ["specific", "medium", "general"]}}],
"title": "same or corrected title"}}"""
    try:
        checked = generate_json(prompt, temperature=0.2)
        scenes = checked.get("scenes") or []
        if len(scenes) == len(script["scenes"]) and all(s.get("narration") for s in scenes):
            if checked.get("problems_found"):
                print(f"[writer] Fact-check fixed: {checked['problems_found']}")
            script["scenes"] = [
                {"narration": s["narration"], "footage_query": o["footage_query"],
                 "footage_queries": o.get("footage_queries", [o["footage_query"]])}
                for s, o in zip(scenes, script["scenes"])
            ]
            if checked.get("title"):
                script["title"] = checked["title"]
    except Exception as exc:  # noqa: BLE001
        print(f"[writer] Fact-check skipped ({exc})")
    return script


def _normalize(script):
    """Repairs small format slips of the model instead of throwing the whole draft away.
    Returns None only if the draft is really unusable (no scenes / no text / no title)."""
    if isinstance(script, list) and script and isinstance(script[0], dict):
        script = script[0]
    if not isinstance(script, dict):
        return None
    scenes = script.get("scenes")
    if not isinstance(scenes, list):
        return None
    fixed = []
    for s in scenes:
        if isinstance(s, str):
            s = {"narration": s}
        if not isinstance(s, dict) or not str(s.get("narration", "")).strip():
            continue
        queries = s.get("footage_queries") or s.get("footage_query") or []
        if isinstance(queries, str):
            queries = [queries]
        queries = [q.strip() for q in queries if isinstance(q, str) and q.strip()] or ["dark forest night"]
        fixed.append({"narration": str(s["narration"]).strip(), "footage_queries": queries[:3], "footage_query": queries[0]})
    if len(fixed) < 2:
        return None
    if len(fixed) > 8:  # merge surplus scenes into the last one
        extra = " ".join(f["narration"] for f in fixed[7:])
        fixed = fixed[:7]
        fixed[-1]["narration"] += " " + extra
    script["scenes"] = fixed
    if not str(script.get("title", "")).strip():
        script["title"] = fixed[0]["narration"].split(".")[0][:60]
    return script


def _expand(script, words):
    """Asks the model to lengthen an existing draft (more reliable than rewriting from scratch)."""
    prompt = f"""This YouTube Short narration has only {words} words but needs {cfg.MIN_WORDS}-{cfg.MAX_WORDS}.
Expand it to about {cfg.MIN_WORDS + 10} words: add atmosphere, sensory detail and tension inside the existing
scenes. Keep the same number of scenes, the same facts, the opening hook and the closing question.

Script JSON:
{script}

Return the same JSON structure with the longer narration."""
    try:
        longer = _normalize(generate_json(prompt, system=SYSTEM, temperature=0.7))
        if longer and len(longer["scenes"]) == len(script["scenes"]):
            for new, old in zip(longer["scenes"], script["scenes"]):
                new["footage_queries"], new["footage_query"] = old["footage_queries"], old["footage_query"]
            return longer
    except Exception as exc:  # noqa: BLE001
        print(f"[writer] Expanding failed ({exc})")
    return script


def _finish(script, series, topic):
    if not series["fiction"]:
        script = _fact_check(script, topic)
    script["title"] = re.sub(r"[#<>]", "", str(script["title"])).strip()[:95]
    script["tags"] = [str(t)[:40] for t in script.get("tags", [])][:15]
    print(f"[writer] Script ready: '{script['title']}' ({word_count(full_narration(script))} words)")
    return script


def write_script(series, topic, feedback="", performance_hint=""):
    best = None
    for attempt in range(3):
        try:
            raw = generate_json(_script_prompt(series, topic, feedback, performance_hint), system=SYSTEM, temperature=0.9)
        except Exception as exc:  # noqa: BLE001
            print(f"[writer] Draft {attempt + 1}: no answer ({exc})")
            continue
        script = _normalize(raw)
        if not script:
            print(f"[writer] Draft {attempt + 1}: unusable structure, retrying")
            continue
        words = word_count(full_narration(script))
        if words < cfg.MIN_WORDS - 8:
            print(f"[writer] Draft {attempt + 1}: only {words} words -> expanding")
            script = _expand(script, words)
            words = word_count(full_narration(script))
        if words > cfg.MAX_WORDS + 15:
            print(f"[writer] Draft {attempt + 1}: {words} words, too long -> rewriting")
            feedback = f"Your previous draft had {words} words - far too long. Stay under {cfg.MAX_WORDS} words."
            if best is None or abs(words - cfg.MAX_WORDS) < abs(best[0] - cfg.MAX_WORDS):
                best = (words, script)
            continue
        if words < cfg.MIN_WORDS - 8:
            print(f"[writer] Draft {attempt + 1}: still only {words} words -> rewriting")
            feedback = f"Your previous draft had only {words} words. Write at least {cfg.MIN_WORDS} words."
            if best is None or words > best[0]:
                best = (words, script)
            continue
        return _finish(script, series, topic)
    # Never give up on a usable draft: the length check after the voice recording decides the rest.
    if best and 70 <= best[0] <= cfg.MAX_WORDS + 40:
        print(f"[writer] Using best draft ({best[0]} words) after 3 attempts")
        return _finish(best[1], series, topic)
    raise RuntimeError("Could not produce a valid script.")
