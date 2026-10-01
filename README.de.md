[English](README.md) | [Deutsch](README.de.md)

![OpenLips](assets/branding/concept-01/openlips-logo-light.png#gh-light-mode-only)
![OpenLips](assets/branding/concept-01/openlips-logo-dark.png#gh-dark-mode-only)

# OpenLips

**Du wolltest schon immer deine eigenen Songs in Lips importieren? Selbst wenn nicht: Jetzt kannst du es zumindest ausprobieren.**

OpenLips ist ein unabhängiges Community-Projekt, das neue Songs in das Xbox-360-Karaokespiel *Lips* bringen möchte. **OpenLips Studio** ist das Programm, das diesen Gedanken umsetzen soll: einen Chart importieren, Noten und Songtext bearbeiten und den Song für das Spiel vorbereiten. Als Ausgangspunkt können UltraStar- oder MIDI-Dateien dienen. Du kannst aber auch einen eigenen Chart erstellen.

Das Ganze befindet sich **noch in einer frühen Entwicklungsphase**. Es gibt eine funktionierende Grundlage, aber vieles ist noch unvollständig, experimentell oder muss gründlicher getestet werden.

> **Inoffiziell und unabhängig.** OpenLips steht in keiner Verbindung zu Microsoft, Xbox oder iNiS. Für die Nutzung und Weitergabe deines Materials brauchst du die nötigen Rechte. Mehr dazu unter [Rechte und Verantwortung](#unabhängigkeit-rechte-und-verantwortung).

## Warum es dieses Projekt gibt

Ich bin Gerrit. Als ich jünger war, habe ich Lips oft mit Freunden gespielt. Seit Jahren wünsche ich mir, unsere eigenen Songs ins Spiel bringen zu können. Irgendwann wollte ich herausfinden, ob aus diesem Wunsch tatsächlich etwas werden kann.

Inzwischen sind viele Stunden, Tage und Monate in das Verstehen der Dateien, in Tests, Irrwege und neue Versuche geflossen. Der entscheidende Schritt war, eigene Chart- und Lyric-Dateien von Grund auf zu erzeugen, die das originale Lips von 2008 im Test laden und abspielen konnte. Zum ersten Mal in diesem Projekt gibt es damit nicht nur ein funktionierendes Ergebnis, sondern auch eine Dokumentation, die den Weg dorthin nachvollziehbar macht.

Ursprünglich habe ich eine Ausbildung zum Informationselektroniker gemacht, also in einem IT-nahen Bereich. Später habe ich den Beruf gewechselt und arbeite heute als Lokführer. Die Begeisterung für Computer, Server und Systeme ist geblieben, ebenso wie viel praktische Erfahrung damit. Programmieren habe ich dagegen nie grundlegend gelernt. Neben meinem Hauptberuf fehlt mir die Zeit, damit ganz von vorn anzufangen. KI-gestützte Entwicklung hat mir die Möglichkeit gegeben, aus einer Idee, die immer liegen geblieben ist, ein echtes Projekt zu machen.

Als Lokführer kenne ich die Sorge vor Automatisierung selbst. Ich habe durchaus Bammel davor, irgendwann durch einen Computer ersetzt zu werden oder nur noch daneben zu sitzen, während der Zug von allein fährt. Die Sorgen von Entwicklern darüber, was KI für ihren Beruf bedeuten könnte, sind für mich deshalb keine abstrakte Diskussion. Auch ihre Bedenken zur Qualität solcher Software kann ich nachvollziehen. Ihre Erfahrung wird dadurch für mich nicht überflüssig. Dieses Projekt baut darauf auf. Und es geht hier auch nicht darum, einmal „mach alles, aber bitte ohne Fehler“ in einen Chat zu schreiben: Dahinter stecken viel Recherche, praktische Tests, Fehlersuche und Dokumentation. Fehler müssen trotzdem gefunden und behoben werden.

Genau deshalb möchte ich das Projekt jetzt öffnen. Aus OpenLips soll mehr werden als mein persönliches Experiment. Wenn du dich für Lips, Karaoke, Reverse Engineering oder nützliche Werkzeuge begeisterst, bist du herzlich eingeladen, mitzumachen.

## Mach mit

Etwas funktioniert nicht? Bitte [melde es](https://github.com/gerrit117/OpenLips-Studio/issues). Beschreibe, was du versucht hast, was passiert ist, welche Version du verwendet hast und möglichst auch, wie sich der Fehler nachstellen lässt. Lade bitte keine urheberrechtlich geschützten Songs oder originalen Spieldateien in öffentliche Fehlerberichte hoch.

Ideen, Korrekturen an der Dokumentation, Tests auf anderen Systemen und [Pull Requests](https://github.com/gerrit117/OpenLips-Studio/pulls) sind genauso willkommen. Du musst nicht programmieren können, um etwas beizutragen. Gerade in dieser frühen Phase ist Rückmeldung keine Störung, sondern die Grundlage dafür, dass das Projekt besser wird.

## Roadmap

Das sind Vorhaben, keine Zusagen für das nächste Release. Die ersten Schwerpunkte sind:

- [x] Eine aktivierbare Plugin-Verwaltung mit `.opl`-Paketen, Einstellungen, Vorschau und Import im Hintergrund einbauen.
- [ ] Das Songformat tiefergehend dokumentieren, einschließlich LS2 und späterer Veröffentlichungen.
- [ ] Quick-Time-Events (QTEs) und weitere songbezogene Spielaktionen unterstützen.
- [ ] Eine Community-Webseite mit Benutzerkonten und einer gemeinsamen Datenbank für selbst erstellte Charts und Lyrics aufbauen, mit den nötigen Nutzungsrechten und Moderationsregeln.
- [x] Spotifys [Basic Pitch](https://github.com/spotify/basic-pitch) einbinden: Gesang in einen MIDI- und Notenentwurf umwandeln, der geprüft und bearbeitet werden kann.
- [ ] Die Plugin-Schnittstelle um weitere Verarbeitungs- und Exportabläufe erweitern.
- [ ] Eigene DLCs zuverlässig installieren und vom Spiel erkennen lassen, auch mit bestehenden Profilen.
- [ ] Medienvorbereitung und Songexport zu einem einfacheren Ablauf zusammenführen und die Konvertierung auf weiteren Plattformen unterstützen.
- [ ] Einen optionalen FTP-Upload für eine kompatible Xbox-Umgebung ergänzen.
- [ ] Bedienbarkeit, Übersetzungen, Barrierefreiheit und Tests im Alltag verbessern.

Mit „LS2“ sind hier die Lips-Veröffentlichungen nach dem ersten Spiel von 2008 gemeint. Ihre Song- und DLC-Strukturen müssen trotzdem einzeln geprüft werden; wir gehen nicht davon aus, dass alle identisch sind.

Einige Grundlagen sind bereits vorhanden:

- [x] UltraStar-Charts und MIDI-Melodien importieren.
- [x] Noten, Silben und Phrasengrenzen in einem grafischen Editor bearbeiten.
- [x] Unfertige Arbeit als `.olp`-Projekt speichern.
- [x] Neue Chart- und Lyric-Dateien für das originale Lips ohne Songvorlage erzeugen.
- [x] Native Beta-Downloads für Windows, macOS und Linux bereitstellen.

## Was Studio heute schon kann

![OpenLips Studio](assets/branding/concept-01/logo-light.png#gh-light-mode-only)
![OpenLips Studio](assets/branding/concept-01/logo-dark.png#gh-dark-mode-only)

- **Importieren oder selbst erstellen.** UltraStar-TXT-Dateien einlesen, eine Melodiespur aus einer MIDI-Datei auswählen oder eigene Noten hinzufügen. Beim UltraStar-Import bleiben das Timing und die Silben erhalten.
- **Mit einer Aufnahme anfangen.** Basic Pitch in der Plugin-Verwaltung aktivieren, eine Audiodatei auswählen und Erkennungsschwellen, Notendauer sowie Tonumfang einstellen. Den lokal erzeugten Entwurf prüfen, als MIDI speichern oder die Noten in den Editor übernehmen. Die Analyse lässt sich abbrechen; die Notenübernahme lässt sich rückgängig machen. Eine isolierte Gesangsspur eignet sich besser als ein vollständiger Mix. Gesangstrennung und Songtexterkennung übernimmt das Plugin nicht.
- **Den Chart bearbeiten.** Noten erstellen, löschen, verschieben oder in ihrer Länge ändern, die Tonhöhe anpassen, Textfragmente zuordnen sowie Wortenden, Phrasen und Seitenwechsel festlegen. Änderungen lassen sich rückgängig machen und wiederholen.
- **Synchronisierte Songtexte behalten.** Die Entwicklungsversion importiert LRC-Dateien und synchronisierte LRCLIB-Ergebnisse, zeigt Zeilen- und Wort-Zeitmarken zur Prüfung an und speichert sie im Projekt. Die automatische KI-Zuordnung ist noch in Arbeit.
- **Das Timing prüfen.** Referenzaudio oder ein Video zusammen mit dem Chart abspielen. Die Wiedergabegeschwindigkeit ändern, hineinzoomen und bei Bedarf alle Noten samt Seitenwechseln zeitlich verschieben.
- **Den Zwischenstand speichern.** Mit einem `.olp`-Projekt kannst du einen Song unfertig lassen und später daran weiterarbeiten. Verknüpfte Medien bleiben separate Dateien.
- **Die Darstellung vorbereiten.** Ein Cover auswählen oder ein einfaches Cover erzeugen lassen. Unter Windows lassen sich Medien für das originale Lips vorbereiten, auf Wunsch auch als statisches Covervideo. Dafür wird derzeit eine separate FFmpeg-Installation benötigt.
- **Exportieren und ausprobieren.** Neue Chart- und Lyric-Dateien exportieren. Das Erstellen von DLC-Paketen ist experimentell vorhanden; die zuverlässige Erkennung im Spiel ist noch nicht fertig.

![Der Charteditor von OpenLips Studio](assets/screenshots/studio-editor.png)

*Der Editor mit einem kleinen, selbst erstellten Demo-Chart.*

![Startzeit, Länge, Tonhöhe, Silbe und Phrasengrenze einer Note bearbeiten](assets/screenshots/studio-note-details.png)

*Für jede Note lassen sich Timing, Tonhöhe und Textzuordnung bearbeiten.*

![Basic-Pitch-Einstellungen und ein synthetischer Notenentwurf](assets/screenshots/studio-plugins.png)

*Das erste Plugin mit einer selbst erzeugten Aufnahme aus vier Testtönen, nicht mit einem Song.*

### Was noch nicht fertig ist

Die bestätigten Tests des gesamten Ablaufs wurden mit dem originalen Lips von 2008 in Xenia durchgeführt. Spätere Veröffentlichungen, sämtliche Spielmodi und die Spielaktionen der Originalsongs werden noch nicht vollständig unterstützt. Ein funktionierender Chartexport ist noch kein fertiger „alles importieren und sofort spielen“-Ablauf. Er macht unsignierte Inhalte auch nicht auf einer unveränderten Xbox 360 installierbar.

Die Medienkonvertierung richtet sich derzeit an den getesteten Wiedergabeweg des ersten Spiels unter Windows. Bearbeitung und Chartexport sind auch unter macOS und Linux verfügbar. Automatische DLC-Audiokonvertierung, zuverlässige DLC-Erkennung und die Community-Webseite sind noch in Arbeit. Wenn etwas nicht klappt, melde es bitte, statt davon auszugehen, dass du etwas falsch gemacht hast.

### Medien unter macOS und Linux

**Für den Spieleexport müssen Audio und gegebenenfalls Video vorerst bereits im kompatiblen Format vorliegen.** MP3-/MP4-Dateien lassen sich im Editor als Referenz verwenden, werden auf diesen Systemen aber nicht automatisch in Lips-Medien umgewandelt.

Das getestete Videoprofil für das erste Spiel ist **ASF `.wmv`, VC-1 Advanced (WVC1), 768 × 432 bei 24000/1001 fps**, mit **WMA-Pro-Audio, 48 kHz, Stereo, 16 Bit und 192 kbit/s**. Separates OG-Audio verwendet ASF/WMA Pro in `.wma`. Die experimentelle DLC-Verpackung benötigt dagegen **RIFF/XWMA für Vollaudio und Vorschau**; das Umbenennen einer `.wma` konvertiert sie nicht. Video ist optional. Originaldateien enthalten außerdem WMV3-Video und WMA-Standard-/xWMA-Audio, aber diese Beobachtungen bestätigen nicht jede neu codierte Datei.

Die [genauen Medienanforderungen und Vorbereitungsschritte](docs/studio_media.md#deutsch-medien-vorbereiten) erläutern auch die Header-Vorgaben und den Unterschied zwischen getesteten Einstellungen und der 720p-Obergrenze.

## Download

Die aktuelle Beta findest du unter **[GitHub Releases](https://github.com/gerrit117/OpenLips-Studio/releases)**. Es gibt Builds für Windows, macOS auf Apple Silicon und Intel sowie Linux.

Entpacke das vollständige Studio-Archiv und lass die enthaltenen Dateien zusammen. Python ist enthalten. Basic Pitch ist ein separater, optionaler **`.opl`**-Download für deine Plattform und wird über die Plugin-Verwaltung installiert. Das Paket enthält sein eigenes Modell und die Analyseumgebung. Eine zusätzliche Python-Installation, ein Spotify-Konto oder ein API-Schlüssel sind nicht nötig. Die Audiodatei wird lokal verarbeitet und nicht hochgeladen. Weitere Informationen stehen im [Plugin-Katalog](plugins/README.md), der [Editor-Anleitung](docs/studio.md), der [Plugin-Entwicklerdokumentation](docs/studio_plugins.md) und den [Plattformhinweisen](docs/studio_platforms.md). Die technische Dokumentation ist derzeit überwiegend auf Englisch.

## Dokumentation

Die technischen Informationen liegen in [`docs/`](docs/). Gute Einstiegspunkte sind:

- [Den Editor verwenden](docs/studio.md).
- [Medien, Cover und Synchronisierung](docs/studio_media.md).
- [Aufbau der Songdateien](docs/structures.md) und der [strukturelle Reader](docs/og_ixb_reader.md).
- [Seitenwechsel und Projekte](docs/studio_pages_and_community.md).
- [Recherche und Kommandozeilenwerkzeuge](docs/research_overview.md).

Die Recherche hält sowohl Erkenntnisse als auch offene Fragen fest. Ein Format lesen zu können bedeutet noch nicht, jede Variante davon sicher schreiben zu können.

## Danke

Ohne Menschen, die ihr Handwerk gelernt, diese Werkzeuge entwickelt und ihre Arbeit geteilt haben, könnte ich dieses Projekt nicht umsetzen. Ihre Zeit und ihr Wissen verdienen Anerkennung, gerade bei einem Projekt wie diesem.

Die App und ihre Entwicklungswerkzeuge bauen auf [Python](https://www.python.org/), [Qt for Python](https://doc.qt.io/qtforpython-6/), [Mido](https://github.com/mido/mido), [Pyphen](https://github.com/Kozea/Pyphen), [QtAwesome](https://github.com/spyder-ide/qtawesome) und [PyInstaller](https://pyinstaller.org/) auf. [LRCLIB](https://lrclib.net/) ermöglicht die optionale Lyrics-Suche; [FFmpeg](https://ffmpeg.org/) hilft bei der optionalen Medienvorbereitung.

Für Recherche und Tests waren auch [Xenia](https://github.com/xenia-project/xenia), [Xenia Canary](https://github.com/xenia-canary/xenia-canary), [Ghidra](https://github.com/NationalSecurityAgency/ghidra) und [XEXLoaderWV](https://github.com/zeroKilo/XEXLoaderWV) wichtig. Der experimentelle Paket-Builder verwendet [Velocity](https://github.com/hetelek/Velocity) und [Botan](https://botan.randombit.net/). Nicht alle diese Werkzeuge sind im App-Download enthalten.

Danke auch an alle, die einen Build testen, Fehler melden, Erkenntnisse teilen oder anderen beim Einstieg helfen. Die Lizenzen und Hinweise zu Abhängigkeiten stehen in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Ein besonderes Dankeschön geht an **Spotifys Audio Intelligence Lab und die Entwickler von [Basic Pitch](https://github.com/spotify/basic-pitch)**, die ihr Transkriptionsmodell und den Quellcode als Open Source bereitstellen. Das erste integrierte Studio-Plugin nutzt ihre Arbeit über [ONNX Runtime](https://github.com/microsoft/onnxruntime). Die Einbindung ist unabhängig und weder ein Spotify-Dienst noch eine offizielle Unterstützung durch Spotify.

Danke auch an **Markus Böhning und die Mitwirkenden von [USDB Syncer](https://github.com/bohning/usdb_syncer)** sowie an das [yt-dlp](https://github.com/yt-dlp/yt-dlp)-Team. Ein eigenständiges USDB-Downloader-Plugin ist in Entwicklung und nutzt die bestehende Such- und Downloadoberfläche. Native Plugin-Pakete und Tests mit angemeldeten Downloads stehen noch aus.

## Unabhängigkeit, Rechte und Verantwortung

**OpenLips und OpenLips Studio sind unabhängige, inoffizielle Projekte. Sie stehen in keiner Verbindung zu Microsoft, Xbox, iNiS, den Entwicklern oder Herausgebern von Lips oder anderen Rechteinhabern und werden von diesen weder unterstützt noch gesponsert.** Produkt- und Firmennamen dienen lediglich dazu, die betreffenden Spiele und Werkzeuge zu benennen. Die jeweiligen Rechte verbleiben bei ihren Inhabern.

**Du bist selbst dafür verantwortlich, dein Ausgangsmaterial rechtmäßig zu beschaffen und zu verwenden.** Das betrifft Spieldateien, Musikaufnahmen, Videos, Coverbilder, Songtexte und musikalische Transkriptionen. Auch Charts und Lyrics ohne beigefügte Aufnahme können urheberrechtlich geschützt sein. Die Software verschafft dir keine zusätzlichen Rechte an Songs oder Spielinhalten. Der Besitz einer Aufnahme allein gibt dir keine Weiterverbreitungsrechte.

OpenLips ist keine Bezugsquelle für Spieldateien oder kommerziell veröffentlichte Songs. Die Softwarelizenz des Projekts gilt nicht für importierte Inhalte. Teile bitte nur Inhalte, für deren Weitergabe du die nötigen Rechte besitzt, und beachte die Gesetze, die für dich gelten.

Der Quellcode des Projekts steht unter [GPL-3.0-or-later](LICENSE).
