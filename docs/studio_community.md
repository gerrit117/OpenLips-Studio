# Community workspace

Studio's **Community** tab connects to `https://openlips.org`. It requires an
OpenLips account with a confirmed email address. Registration and initial 2FA
setup open the official website in your browser. There is no embedded web view.
Administrators and moderators must also verify their authenticator code; no
desktop bypass is provided. Maintenance access and staff session deadlines are
enforced by the server, not by hiding buttons in Studio.

After signing in, search titles, artists and albums, sort results and navigate
pages. Select a song to see its description, rating and comments. **My uploads**
also includes your pending or rejected submissions. Published songs can be rated
from 1 to 5. This version displays comments; posting them remains on the website.

**Download and open** asks where to save the .ols song. Studio validates its
format, native chart/lyric pair and cover before writing it, never overwrites an
existing file, and asks about unsaved editor work before replacing it. No audio
or video is downloaded from the community. Acquire any referenced media lawfully
using Studio's separate media workflow.

The Upload tab accepts an existing .ols song, reads its embedded metadata, and
requires confirmation that you may share the lyrics, chart and cover. Alternatively,
**Upload current song** exports a temporary media-free bundle with your selected
metadata and sends it directly. Your project and source media remain unchanged.
All uploads pass the website's isolated validation and await moderation before
appearing in the public catalog. .olp remains a local project format, not an upload.

Connections use certificate-verified HTTPS, bounded responses, the website's
session cookies and CSRF tokens. Unexpected redirects are rejected, including
cross-origin redirects. Credentials, session cookies and CSRF tokens are held in
memory only and discarded when Studio exits. They are not saved in projects,
preferences or logs. Network/file work runs in a background thread. Studio waits
for an active operation to finish before closing or rebuilding the UI language.

## API contract

Desktop requests use `/api/studio/v1/`. `GET session/` supplies a CSRF token and
session phase; `POST login/`, `mfa/` and `logout/` rotate or clear it as appropriate.
Subsequent POSTs send `X-CSRFToken`, the official Origin/Referer and session cookies.
`GET songs/` accepts q, sort, page and mine; results contain at most 24 songs.
`GET songs/{id}/`, `GET songs/{id}/download/`, `POST songs/{id}/rate/` and
`POST upload/` provide detail, bounded .ols downloads, ratings and multipart uploads.
The upload's `archive` field holds the .ols file; `rights` must be affirmed.
Metadata is read from the validated manifest, not trusted from arbitrary request fields.

Errors such as maintenance, authentication, 2FA and expiry are returned without
HTML scraping. This is a public protocol description, not website source code;
the backend remains in the separate private repository.

## Deutsch

Im Reiter **Community** mit dem bestätigten OpenLips-Konto anmelden. Admins und
Moderatoren geben zusätzlich ihren Authenticator-Code ein. Im Wartungsmodus bleibt
der Zugriff auf diese Konten beschränkt. Registrierung und die erstmalige
2FA-Einrichtung erfolgen auf der Webseite.

Songs suchen, Bewertungen und Kommentare ansehen, veröffentlichte Songs bewerten
oder als .ols herunterladen und im Editor öffnen. **Meine Uploads** zeigt auch
noch nicht freigegebene Songs. Im Upload-Reiter eine .ols-Datei auswählen oder den
aktuellen Song direkt hochladen. Lyrics, Chart und Cover werden geprüft; Audio und
Video werden nicht mitgeschickt. Die Freigabe erfolgt durch die Moderation.

Anmeldedaten und Sitzungscookies werden nicht auf der Festplatte gespeichert.
Ein Community-Upload ersetzt weder das Speichern eines .olp-Projekts noch einen
DLC-Export. Die Berechtigung zur Weitergabe aller enthaltenen Inhalte ist notwendig.
