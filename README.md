# Lantern Lore – vollautomatischer YouTube-Shorts-Bot

Erstellt bis zu 3× täglich einen englischen Grusel- oder Legenden-Short (45–58 Sekunden) und lädt ihn auf deinen Kanal hoch. Alles läuft kostenlos in GitHub Actions, dein PC muss nicht an sein.

## So arbeitet der Bot bei jedem Lauf
1. **Thema:** wählt eine der 7 Serien (siehe `CHANNEL_PROFILE.md`) und lässt Gemini ein **noch nie verwendetes** Thema finden. Alle bisherigen Themen stehen in `data/published_history.json`, deshalb wiederholt sich nichts. Gehen einer Serie irgendwann die echten Legenden aus, weicht der Bot auf selbst erfundene „Campfire Tales“ aus, und davon gibt es unbegrenzt viele.
2. **Skript:** Gemini schreibt die Erzählung. Bei echten Legenden prüft ein zweiter Durchgang, ob Namen, Daten oder Behauptungen erfunden wurden.
3. **Stimme:** Kokoro (freies Sprachmodell, britischer Erzähler) läuft direkt auf GitHub. Falls das ausfällt, springt Edge-TTS ein.
4. **Bilder:** passende, lizenzfreie Clips von Pexels im einheitlichen dunklen „Lantern Lore“-Look.
5. **Musik:** eigene, im Lauf erzeugte Ambient-Klangfläche, dadurch nie ein Copyright-Claim. Wer möchte, legt eigene lizenzfreie Tracks in `assets/music/`.
6. **Untertitel:** große, wortweise eingeblendete Untertitel, oben das Serien-Label, unten „LANTERN LORE“.
7. **Upload:** über die offizielle YouTube-API, mit KI-Kennzeichnung, Quellenangaben und Hashtags.
8. **Verlauf:** wird ins Repo zurückgespeichert.

## Kosten
0 €. Gemini (kostenloser Tarif), Pexels, Kokoro, Edge-TTS und die YouTube-API sind kostenlos. GitHub Actions ist in einem privaten Repo bis 2.000 Minuten im Monat kostenlos; der Bot braucht grob 500–800.

## Einstellungen ohne Code
Unter GitHub → Repo → **Settings → Secrets and variables → Actions → Tab „Variables“**:

| Variable | Wirkung |
|---|---|
| `SHORTS_PER_DAY` | `1`, `2` oder `3` (Standard 3) |
| `LL_PAUSED` | `true` = Bot pausiert, löschen = läuft wieder |
| `GEMINI_MODEL` | nur im Notfall: bestimmtes Gemini-Modell erzwingen |

## Wartung
Der Bot ist darauf ausgelegt, ohne dich zu laufen. Wenn ein Lauf scheitert, schickt GitHub dir automatisch eine E-Mail. Häufige Gründe:
- **Google-Passwort geändert oder App-Zugriff entzogen:** Den Refresh-Token neu erzeugen (Einrichtung Schritt 5) und das Secret `YT_REFRESH_TOKEN` ersetzen.
- **Gemini-Modell abgeschaltet:** Der Bot sucht sich automatisch das neueste verfügbare Flash-Modell. Normalerweise musst du nichts tun.
- **Videos bleiben privat:** siehe unten.

## Videos bleiben privat
Google kann Uploads aus nicht geprüften API-Projekten auf „privat“ sperren. Wenn das passiert, steht im Lauf eine gelbe Warnung. Lösung: Das kostenlose Formular „YouTube API Services – Audit and Quota Extension Form“ ausfüllen (Zweck: „Uploading my own automatically produced videos to my own channel“). Die Prüfung dauert meist einige Tage bis Wochen.

---

# Einrichtung

**A. Schlüssel besorgen.** Die Schritte 1–4 sind unabhängig voneinander und können parallel erledigt werden.

1. **YouTube-Kanal anlegen** (parallel möglich): Im Google-Konto unter youtube.com → Kanal erstellen. Name **Lantern Lore**, Handle **@LanternLore** (Ausweichnamen in `CHANNEL_PROFILE.md`), Beschreibung aus `CHANNEL_PROFILE.md` einfügen.

2. **Gemini-API-Key** (parallel möglich): aistudio.google.com → „Get API key“ → „Create API key“. Den Schlüssel notieren. Es ist keine Kreditkarte nötig; lege kein Abrechnungskonto an, dann bleibt es garantiert kostenlos.

3. **Pexels-API-Key** (parallel möglich): pexels.com/api → kostenloses Konto → API-Key anfordern (Zweck z. B. „Automated YouTube Shorts with stock footage, attribution in description“). Den Schlüssel notieren.

4. **Google-Cloud-Projekt für den Upload** (parallel möglich):
   - console.cloud.google.com → neues Projekt **lantern-lore-bot**.
   - „APIs & Dienste“ → Bibliothek → **YouTube Data API v3** aktivieren.
   - „Google Auth Platform“ bzw. „OAuth-Zustimmungsbildschirm“ → Typ **Extern**, App-Name „Lantern Lore Bot“, deine E-Mail als Support- und Entwickleradresse. Unter „Datenzugriff“ bzw. „Bereiche“ den Bereich `https://www.googleapis.com/auth/youtube.upload` hinzufügen.
   - **Wichtig:** Unter „Zielgruppe“ bzw. „Veröffentlichungsstatus“ auf **„App veröffentlichen“ / „In Produktion“** stellen. Bleibt die App im Testmodus, läuft der Zugang nach 7 Tagen ab und der Bot stoppt. Die Warnung „App nicht überprüft“ ist für die eigene Nutzung in Ordnung.
   - „Clients“ bzw. „Anmeldedaten“ → **OAuth-Client-ID erstellen** → Typ **Webanwendung** → bei „Autorisierte Weiterleitungs-URIs“ genau `https://developers.google.com/oauthplayground` eintragen → Client-ID und Clientschlüssel notieren.

5. **Refresh-Token holen** (wartet auf Schritt 1 und 4):
   - developers.google.com/oauthplayground öffnen → Zahnrad oben rechts → Haken bei **„Use your own OAuth credentials“** → Client-ID und Clientschlüssel aus Schritt 4 einfügen.
   - Links unten ins Feld „Input your own scopes“ `https://www.googleapis.com/auth/youtube.upload` eintragen → **Authorize APIs**.
   - Mit dem Google-Konto anmelden und **den Kanal Lantern Lore auswählen**. Bei „Google hat diese App nicht überprüft“ auf „Erweitert“ → „Weiter zu Lantern Lore Bot“ → Zugriff erlauben.
   - Bei Step 2 auf **„Exchange authorization code for tokens“** klicken und den **Refresh token** notieren.

**B. GitHub**

6. **Repo anlegen und Dateien hochladen** (unabhängig von 1–5, parallel möglich): Auf GitHub ein **privates** Repo `lantern-lore-shorts` anlegen (leer, ohne README). Das ZIP entpacken, z. B. nach `C:\Projekte\lantern-lore-shorts`, dann in PowerShell ausführen:
   ```powershell
   cd "C:\Projekte\lantern-lore-shorts"
   git init
   git add -A
   git commit -m "Lantern Lore: automatischer YouTube-Shorts-Bot"
   git branch -M main
   git remote add origin https://github.com/DEIN-GITHUB-NAME/lantern-lore-shorts.git
   git push -u origin main
   ```

7. **Secrets eintragen** (wartet auf 2, 3, 4, 5 und 6): Repo → Settings → Secrets and variables → Actions → „New repository secret“, fünfmal:
   - `GEMINI_API_KEY` (aus Schritt 2)
   - `PEXELS_API_KEY` (aus Schritt 3)
   - `YT_CLIENT_ID` (aus Schritt 4)
   - `YT_CLIENT_SECRET` (aus Schritt 4)
   - `YT_REFRESH_TOKEN` (aus Schritt 5)

8. **Testvideo ohne Upload** (wartet auf 7): Repo → Actions → Workflow **„Lantern Lore - Short erstellen und hochladen“** → „Run workflow“, Haken bei „Auf YouTube hochladen?“ **nicht** setzen → starten. Nach ca. 8–12 Minuten unten auf der Lauf-Seite unter „Artifacts“ **lantern-lore-short** herunterladen und das Video ansehen.

9. **Echter Test-Upload** (wartet auf 8): Denselben Workflow noch einmal starten, diesmal **mit** Haken bei „Auf YouTube hochladen?“. Danach in YouTube Studio prüfen, ob das Video **öffentlich** ist.

Danach läuft alles automatisch, 3× täglich.
