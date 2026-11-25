# Lantern Lore – vollautomatischer YouTube-Shorts-Bot

Erstellt bis zu 3× täglich einen englischen Grusel- oder Legenden-Short (45–58 Sekunden) und lädt ihn auf deinen Kanal hoch. Alles läuft kostenlos in GitHub Actions, dein PC muss nicht an sein.

## So arbeitet der Bot bei jedem Lauf
1. **Thema:** wählt eine der 7 Serien (siehe `CHANNEL_PROFILE.md`) und lässt Gemini ein **noch nie verwendetes** Thema finden. Alle bisherigen Themen stehen in `data/published_history.json`, deshalb wiederholt sich nichts. Gehen einer Serie irgendwann die echten Legenden aus, weicht der Bot auf selbst erfundene „Campfire Tales“ aus, und davon gibt es unbegrenzt viele.
2. **Skript:** Gemini schreibt die Erzählung. Bei echten Legenden prüft ein zweiter Durchgang, ob Namen, Daten oder Behauptungen erfunden wurden.
3. **Stimme:** Kokoro (freies Sprachmodell, britischer Erzähler) läuft direkt auf GitHub. Falls das ausfällt, springt Edge-TTS ein.
4. **Bilder:** passende, lizenzfreie Clips von Pixabay (optional zusätzlich Pexels) im einheitlichen dunklen „Lantern Lore“-Look. Findet sich nichts oder ist der Dienst gestört, erzeugt der Bot selbst einen dunklen Nebel-Hintergrund. Der Upload fällt also nie aus.
5. **Musik:** eigene, im Lauf erzeugte Ambient-Klangfläche, dadurch nie ein Copyright-Claim. Wer möchte, legt eigene lizenzfreie Tracks in `assets/music/`.
6. **Untertitel:** große, wortweise eingeblendete Untertitel, oben das Serien-Label, unten „LANTERN LORE“.
7. **Upload:** über die offizielle YouTube-API, mit KI-Kennzeichnung, Quellenangaben und Hashtags.
8. **Verlauf:** wird ins Repo zurückgespeichert.

## Wachstums-Funktionen
- **Starke Einstiege:** Der erste Satz hat höchstens 12 Wörter und springt direkt in den unheimlichsten Moment der Geschichte.
- **Frage am Ende:** Jeder Short endet mit einer kurzen Frage an die Zuschauer, das bringt mehr Kommentare.
- **Playlists pro Serie:** Jeder Short landet automatisch in der Playlist seiner Serie.
- **Selbstoptimierung:** Vor jedem Short lädt der Bot die Aufrufe, Likes und Kommentare der letzten 60 Tage. Serien, die gut laufen, kommen häufiger (bis 2×), schwache seltener (bis 0,5×). Die besten Titel bekommt Gemini als Stilvorbild.
- **Wochen-Kompilation:** Jeden Sonntag erzählt der Bot die besten 6–12 Shorts der letzten Wochen als 16:9-Langvideo (ca. 8–12 Minuten) neu, mit Kapiteln, Thumbnail und eigener Playlist („Legends to Fall Asleep To“). Lange Videos sammeln die Wiedergabestunden, die YouTube für die Monetarisierung verlangt.

Playlists und Statistik brauchen die Berechtigung `https://www.googleapis.com/auth/youtube`. Fehlt sie, lädt der Bot trotzdem hoch und überspringt nur diese Extras (gelbe Warnung im Lauf). Eigene Thumbnails setzt YouTube nur bei telefonisch verifizierten Kanälen (youtube.com/verify).

## Kosten
0 €. Gemini (kostenloser Tarif), Pixabay, Kokoro, Edge-TTS und die YouTube-API sind kostenlos. GitHub Actions ist in einem privaten Repo bis 2.000 Minuten im Monat kostenlos; der Bot braucht grob 500–800.

## Einstellungen ohne Code
Unter GitHub → Repo → **Settings → Secrets and variables → Actions → Tab „Variables“**:

| Variable | Wirkung |
|---|---|
| `SHORTS_PER_DAY` | `1`, `2` oder `3` (Standard 3) |
| `LL_PAUSED` | `true` = Bot pausiert, löschen = läuft wieder |
| `GEMINI_MODEL` | nur im Notfall: bestimmtes Gemini-Modell erzwingen |

Workflows:
- **„Lantern Lore - Short erstellen und hochladen“**: 3× täglich
- **„Lantern Lore - Wochen-Kompilation erstellen und hochladen“**: sonntags 17:37 Uhr (deutsche Zeit)

## Wartung
Der Bot ist darauf ausgelegt, ohne dich zu laufen. Wenn ein Lauf scheitert, schickt GitHub dir automatisch eine E-Mail. Häufige Gründe:
- **Google-Passwort geändert oder App-Zugriff entzogen:** Den Refresh-Token neu erzeugen (Einrichtung Schritt 5) und das Secret `YT_REFRESH_TOKEN` ersetzen.
- **Gemini-Modell abgeschaltet:** Der Bot sucht sich automatisch das neueste verfügbare Flash-Modell. Normalerweise musst du nichts tun.
- **Videos bleiben privat:** siehe unten.

## Videos bleiben privat
Google kann Uploads aus nicht geprüften API-Projekten auf „privat“ sperren. Wenn das passiert, steht im Lauf eine gelbe Warnung. Lösung: Das kostenlose Formular „YouTube API Services – Audit and Quota Extension Form“ ausfüllen (Zweck: „Uploading my own automatically produced videos to my own channel“). Die Prüfung dauert meist einige Tage bis Wochen.

---

# Einrichtung

## Schritt 3 – Pixabay-API-Key (statt Pexels)
pixabay.com → kostenlos registrieren und einloggen → **pixabay.com/api/docs** öffnen. Im Abschnitt „Parameters“ steht beim Parameter `key` dein persönlicher Schlüssel (grün hinterlegt, z. B. `12345678-0a1b2c3d4e5f…`). Den Schlüssel kopieren.

## Schritt 4 – Google-Cloud-Projekt fertig einrichten
Projekt und „YouTube Data API v3“ hast du schon. Achte oben links darauf, dass dein Projekt ausgewählt ist.

**4a – Zustimmungsbildschirm anlegen**
1. Menü ☰ → **APIs & Dienste** → **OAuth-Zustimmungsbildschirm**. Es öffnet sich die „Google Auth Platform“. Dort auf **„Jetzt starten“ / „Get started“** klicken.
2. *App-Informationen:* App-Name `Lantern Lore Bot`, Nutzersupport-E-Mail = deine Gmail → Weiter.
3. *Zielgruppe:* **Extern** → Weiter.
4. *Kontaktdaten:* deine Gmail → Weiter.
5. *Abschließen:* Haken bei den Richtlinien → Weiter → **Erstellen**.

**4b – Berechtigung (Scope) hinzufügen**
1. Links im Menü der Google Auth Platform: **Datenzugriff** → **Bereiche hinzufügen oder entfernen**.
2. Ganz unten im Feld **„Bereiche manuell hinzufügen“** einfügen: `https://www.googleapis.com/auth/youtube.upload` und `https://www.googleapis.com/auth/youtube` (eine Zeile pro Scope) → **Zur Tabelle hinzufügen** → **Aktualisieren**.
3. Auf der Seite unten auf **Speichern** klicken.

**4c – App veröffentlichen (wichtig!)**
1. Links: **Zielgruppe**. Dort steht „Veröffentlichungsstatus: Testen“.
2. **App veröffentlichen** → Bestätigen. Danach steht dort „In Produktion“. Ein Hinweis wie „Überprüfung erforderlich“ kann ignoriert werden, weil nur du die App nutzt.

Warum das wichtig ist: Im Status „Testen“ verfällt der Zugang nach 7 Tagen und der Bot hört auf.

**4d – OAuth-Client erstellen**
1. Links: **Clients** → **+ Client erstellen**.
2. Anwendungstyp: **Webanwendung**, Name: `Lantern Lore Uploader`.
3. Unter **Autorisierte Weiterleitungs-URIs** → **+ URI hinzufügen** → genau `https://developers.google.com/oauthplayground` eintragen. Kein Schrägstrich am Ende.
4. **Erstellen**. Es erscheint ein Fenster mit **Client-ID** (endet auf `.apps.googleusercontent.com`) und **Clientschlüssel** (beginnt mit `GOCSPX-`). **Beide sofort kopieren** oder „JSON herunterladen“ klicken. Den Schlüssel zeigt Google später eventuell nicht mehr an; dann einfach einen neuen Client erstellen.

## Schritt 5 – Refresh-Token holen
Wichtig: Im Inkognito-Fenster arbeiten und bei der Kontoauswahl das Brand-Konto des Kanals wählen (bei dir heißt es noch „NarcistiCeXo“).
Als Scopes immer diese beiden eintragen, mit Leerzeichen getrennt:
`https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube`

1. **developers.google.com/oauthplayground** öffnen.
2. Oben rechts auf das **Zahnrad ⚙** klicken. „OAuth flow: Server-side“ und „Access type: Offline“ lassen, Haken bei **„Use your own OAuth credentials“** setzen, dann Client-ID und Clientschlüssel aus 4d einfügen. Fenster schließen.
3. Links bei „Step 1“ ganz unten im Feld **„Input your own scopes“** die beiden Scopes von oben einfügen → **Authorize APIs**.
4. Google-Anmeldung: dein Konto wählen. Wenn gefragt wird, welches Konto bzw. welchen Kanal du nutzen willst: **den Kanal Lantern Lore** wählen.
5. Warnung „Google hat diese App nicht überprüft“: **Erweitert** → **„Weiter zu Lantern Lore Bot (unsicher)“** → **Weiter/Zulassen**. Das ist deine eigene App, daher ungefährlich.
6. Du landest wieder im Playground bei „Step 2“. Auf **„Exchange authorization code for tokens“** klicken.
7. Im Feld **Refresh token** steht ein langer Text, der mit `1//` beginnt. Den Text kopieren.
8. Gegenprobe: Bei **Step 3** als Request URI `https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true` eintragen → **Send the request**. In der Antwort muss `"title": "Lantern Lore"` stehen.

## Schritt 6 – Code auf GitHub
Auf github.com/new ein **privates**, **leeres** Repo `lantern-lore-shorts` anlegen (kein README, kein .gitignore). Dann in PowerShell:
```powershell
cd "E:\dev\lantern-lore-shorts"
git add -A
git commit -m "Pixabay statt Pexels, Nebel-Fallback, Anleitung erweitert"
git remote set-url origin https://github.com/eXoDoze/lantern-lore-shorts.git
git push -u origin main
```

## Schritt 7 – Secrets eintragen
Repo auf GitHub → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**. Für jede Zeile den Namen exakt so eintragen und den Wert einfügen:

| Name | Wert | Woher | Erkennbar an |
|---|---|---|---|
| `GEMINI_API_KEY` | Gemini-Schlüssel | Schritt 2 (aistudio.google.com → „Get API key“) | beginnt mit `AIza` |
| `PIXABAY_API_KEY` | Pixabay-Schlüssel | Schritt 3 (pixabay.com/api/docs) | Zahlen-Bindestrich-Buchstaben |
| `YT_CLIENT_ID` | Client-ID | Schritt 4d | endet auf `.apps.googleusercontent.com` |
| `YT_CLIENT_SECRET` | Clientschlüssel | Schritt 4d | beginnt mit `GOCSPX-` |
| `YT_REFRESH_TOKEN` | Refresh token | Schritt 5 | beginnt mit `1//` |

`PEXELS_API_KEY` ist optional. Sollte Pexels wieder Schlüssel vergeben, kann er später ergänzt werden.

## Schritt 8 – Testvideo ohne Upload
Repo → **Actions** → Workflow **„Lantern Lore - Short erstellen und hochladen“** → **Run workflow**, Haken bei „Auf YouTube hochladen?“ **nicht** setzen → starten. Nach ca. 8–12 Minuten unten auf der Lauf-Seite unter „Artifacts“ **lantern-lore-short** herunterladen.

## Schritt 9 – Echter Upload
Denselben Workflow mit Haken bei „Auf YouTube hochladen?“ starten. Danach in YouTube Studio prüfen, ob das Video **öffentlich** ist. Ab dann läuft alles automatisch.
