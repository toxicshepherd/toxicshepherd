# Setup

Die Profilkarte ist kein Markdown-Codeblock, sondern ein generiertes SVG. Nur so
lassen sich Farben darstellen, und nur so koennen sich die Zahlen selbst
aktualisieren. `generate.py` holt die Statistiken ueber die GitHub-GraphQL-API und
schreibt `dark_mode.svg` und `light_mode.svg`; ein taeglicher Actions-Job committet
das Ergebnis zurueck.

## 1. Repository anlegen

Das Repo muss **exakt so heissen wie dein GitHub-Username** und **public** sein –
nur dann zeigt GitHub das README auf deinem Profil an.

```sh
cd github-profile
git init -b main
git add -A
git commit -m "Profilkarte"
git remote add origin git@github.com:<USERNAME>/<USERNAME>.git
git push -u origin main
```

## 2. Token hinterlegen

Der Standard-`GITHUB_TOKEN` einer Action darf nur das eigene Repo lesen. Fuer
Stars, Commits und Lines of Code ueber alle Repos hinweg brauchst du ein eigenes
Token:

1. **Settings → Developer settings → Personal access tokens → Tokens (classic)**
2. Scopes: `repo` und `read:user`
3. Im Profil-Repo unter **Settings → Secrets and variables → Actions** als
   `ACCESS_TOKEN` speichern.

Ohne `repo` fehlen private Repos in der Statistik. Willst du die gar nicht
mitzaehlen, reicht `public_repo`.

## 3. `config.json` ausfuellen

Alles mit `CHANGE_ME` anpassen, insbesondere `github_username`, `header` und
`birthday` (daraus wird die "Uptime" berechnet).

Platzhalter, die `generate.py` ersetzt:

| Platzhalter     | Bedeutung                                          |
| --------------- | -------------------------------------------------- |
| `{uptime}`      | Zeit seit `birthday`, als Jahre/Monate/Tage        |
| `{login}`       | GitHub-Username laut Token                          |
| `{repos}`       | Eigene Repos ohne Forks                             |
| `{contributed}` | Fremde Repos, zu denen du beigetragen hast          |
| `{stars}`       | Summe aller Stars auf deinen Repos                  |
| `{commits}`     | Deine Commits ueber alle sichtbaren Repos           |
| `{followers}`   | Follower                                            |
| `{loc}`         | Zeilen Code netto (`loc_added` − `loc_deleted`)     |
| `{loc_added}`   | Hinzugefuegte Zeilen                                |
| `{loc_deleted}` | Geloeschte Zeilen                                   |

Farben innerhalb eines Werts: `[[num|42]]`, `[[green|+1]]`, `[[red|-1]]`,
`[[orange|!]]`, `[[muted|nebensache]]`.

## 4. ASCII-Art ersetzen

`ascii_art.txt` enthaelt aktuell eine gerenderte Kugel als Platzhalter. Fuer ein
Portrait:

```sh
pip install Pillow
python3 ascii_from_image.py foto.jpg --width 44 --contrast 1.3
```

Eng beschnittenes Gesicht vor ruhigem Hintergrund funktioniert am besten. Sieht
das Ergebnis aus wie ein Negativ, hilft `--invert`.

## 5. Lokale Vorschau

```sh
python3 generate.py --offline   # rendert mit Nullen, ohne API-Zugriff
```

Mit echten Zahlen:

```sh
ACCESS_TOKEN=ghp_... python3 generate.py
```

Der erste Lauf zaehlt jeden Commit einzeln durch und dauert je nach Anzahl der
Repos ein paar Minuten. Das Ergebnis landet in `cache/loc.json` und wird
mitcommittet; danach werden nur noch Repos neu gezaehlt, deren Commit-Zahl sich
geaendert hat.

## Hinweis zur Sichtbarkeit

Das Repo ist zwingend oeffentlich. Alles in `config.json` ist damit oeffentlich –
also keine internen Hostnamen, IP-Bereiche, Kundennamen oder Server-Details der
Kanzlei-Infrastruktur eintragen. Die Felder `Host` und `Kernel` sind bei
Neofetch-Karten ueblicherweise Arbeitgeber und Rolle, nicht echte Maschinen.

## Fehlersuche

- **Karte aendert sich auf dem Profil nicht:** GitHub cached Bilder aggressiv.
  Ein Reload mit Shift hilft, sonst ein paar Minuten warten.
- **Workflow bricht mit `Secret ACCESS_TOKEN fehlt` ab:** Schritt 2.
- **`GraphQL error: Resource not accessible`:** Dem Token fehlt der Scope `repo`.
- **Werte laufen ueber den rechten Rand:** `card_width` in `config.json` erhoehen
  oder den Wert kuerzen.
