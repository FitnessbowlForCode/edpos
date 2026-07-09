# EDPOS

> Die Video-Apps Apollo und Hermes sind Teil des EDPOS-Projekts.
> Sie stellen einen Proof of Concept dar.

* **Projekt-Webseite:** https://plus-edpos.duckdns.org/
* **Apollo:** https://plus-app1.duckdns.org/
* **Hermes:** https://plus-app2.duckdns.org/

---

## Inhaltsverzeichnis

- [Über das Projekt](#über-das-projekt)
- [Technischer Aufbau](#technischer-aufbau)
- [Features](#features)

---

## Über das Projekt

Apollo und Hermes sind Produkte aus dem EDPOS-Projekt. EDPOS ist eine Initiative, die ausarbeitet, wie Videoplattformen nach europäischen Richtlinien gestaltet sein könnten.

### Was sind Apollo und Hermes?
Apollo und Hermes stellen zwei unabhängige Videoplattformen dar. Im Rahmen des Proof of Concept wurden Apollo und Hermes von zwei unterschiedlichen Unternehmen (theoretisch) entwickelt.

### Wie funktioniert es?
Die Kernfunktion nennt sich Cross-Kompatibilität. Obwohl Apollo und Hermes theoretisch von zwei Unternehmen unabhängig voneinander entwickelt wurden, sind beide Videoplattformen bis zu einem gewissen Grad miteinander verbunden.

### Was bedeutet das?
Videos, Kommentare, Likes und andere Interaktionen werden auf beiden Plattformen synchronisiert und dargestellt. Wenn du beispielsweise Apollo öffnest, bekommst du auch Videos von Hermes vorgeschlagen und umgekehrt.

### Wieso ist das eine Kernfunktion?
In unserem EDPOS-Projekt spielt die digitale Unabhängigkeit Europas eine zentrale Rolle. Wir gehen davon aus, dass Europa es auch zukünftig schwer haben wird, ein einzelnes großes Unternehmen im Bereich der Videoplattformen zu etablieren, das der Konkurrenz aus den USA oder China die Stirn bieten kann.

Wir sehen jedoch Potenzial in vielen kleinen, europäischen Unternehmen. Alleine wären diese zwar nicht konkurrenzfähig, aber durch unser Konzept der Vernetzung bilden sie ein großes Kollektiv, das in der Theorie auch mit den großen Videoplattformen konkurrieren kann.

### Gebaut mit und geschrieben in

* **Frontend:** HTML5, CSS3, JavaScript (als Progressive Web App mit [hls.js](https://github.com/video-dev/hls.js/))
* **Backend:** [Python](https://www.python.org/) (mit [FastAPI](https://fastapi.tiangolo.com/) und [pip](https://pypi.org/))
* **Infrastruktur & Tools:** [Docker](https://www.docker.com/), [MinIO](https://www.min.io/), [WordPress](https://wordpress.org/), [Vikunja](https://vikunja.io/) (https://plus-vikunja.duckdns.org/)
* **Routing & DNS:** [Nginx Proxy Manager](https://nginxproxymanager.com/), [DuckDNS](https://www.duckdns.org/)

---

## Technischer Aufbau

Das Gesamtsystem besteht aus zwei unabhängigen, dezentralen Plattformen (**Apollo** und **Hermes**), die auf separaten virtuellen Servern (VMs) betrieben werden. Beide Instanzen verfügen über ein identisches technologisches Fundament, sind jedoch visuell und datenbankseitig voneinander isoliert. Über eine REST-API sind sie in der Lage, Inhalte plattformübergreifend und in Echtzeit miteinander zu teilen.

### 1. Systemkomponenten (Architektur pro VM)

Jede Instanz ist als containerisierte Microservice-Architektur mittels **Docker Compose** realisiert:

* **PWA-Frontend:** Ein schlankes, responsives HTML5/CSS3-Frontend, das als Progressive Web App (PWA) agiert. Es integriert `hls.js` für das adaptive Videostreaming und kommuniziert via REST-Schnittstellen mit dem Backend.
* **FastAPI-Backend (Python):** Ein performantes, asynchrones Backend, das die API-Endpunkte bereitstellt, die Interaktionslogik steuert und rechenintensive Hintergrundprozesse (Videoskalierung) verwaltet.
* **PostgreSQL-Datenbank:** Relationaler Datenspeicher für Metadaten (Benutzer, Videoregistrierungen, Likes, Views und Kommentare).
* **MinIO (S3 Object Storage):** Lokaler, S3-kompatibler Objektspeicher zur persistenten Ablage der generierten Videosegmente und Thumbnails.
* **Nginx Proxy Manager:** Verwaltet das Routing, übernimmt das SSL-Offloading (Let's Encrypt HTTPS) und bindet die Container über ein isoliertes Docker-Netzwerk an.

---

### 2. Video-Infrastruktur & Adaptive Streaming (HLS)

Um Bandbreite zu schonen und eine flüssige Wiedergabe auf allen Endgeräten zu garantieren, wird kein rohes MP4-Material ausgeliefert. Stattdessen setzt das System auf **HTTP Live Streaming (HLS)**:

1. **Asynchrone Verarbeitung:** Beim Upload einer MP4-Datei nimmt das Backend die Datei entgegen und übergibt die Verarbeitung sofort an einen asynchronen `BackgroundTasks`-Worker, damit der Nutzer nicht blockiert wird.
2. **FFmpeg Multi-Resolution Transcoding:** Das Video wird mittels FFmpeg in drei Qualitätsstufen zerlegt und optimiert:
   * **360p** (640x360) für geringe Bandbreiten.
   * **720p** (1280x720) als HD-Standard.
   * **1080p** (1920x1080) für Full-HD-Wiedergabe.
3. **Segmentierung:** Die Videostreams werden in kurze, 4 Sekunden lange Segmente (`.ts`-Dateien) zerschnitten. Parallel wird eine Master-Playlist (`master.m3u8`) generiert, die als Index für den Videoplayer dient.
4. **S3-Upload:** Alle Segmente, Playlists und ein extrahiertes JPEG-Thumbnail werden mit dynamischen Content-Types in das MinIO-Bucket geladen und in der PostgreSQL-Datenbank registriert.

---

### 3. Dezentrale Föderation & Server-Sharing (Das "Fediverse"-Prinzip)

Die Kernkomponente der Arbeit ist die netzwerkbasierte Föderation. Die Server arbeiten nicht als isolierte Silos, sondern spannen ein gemeinsames Netz auf.

#### Der Video-Feed (Cross-Site-Query)
Wenn ein Benutzer den Video-Feed im Browser aufruft, passiert Folgendes im Hintergrund:
1. Das Backend fragt die lokalen Videos aus der eigenen PostgreSQL-Datenbank ab.
2. Gleichzeitig sendet das Backend über einen asynchronen HTTP-Client (`httpx`) eine Anfrage an den konfigurierten Nachbar-Server (`NEXT_NEIGHBOR_API/videos`).
3. **Endlosschleifen-Schutz (Ping-Pong-Sperre):** Um zu verhindern, dass sich die Server unendlich gegenseitig abfragen, wird ein spezieller HTTP-Header (`X-Federation: True`) mitgesendet. Erkennt ein Backend diesen Header, liefert es *nur* seine eigenen lokalen Videos zurück und fragt nicht erneut seinen Nachbarn ab.
4. Das Backend führt beide Listen zusammen, filtert Duplikate anhand der eindeutigen IDs heraus, sortiert den Feed global nach dem neuesten Zeitstempel und liefert ihn an das Frontend aus.

#### Föderierte Interaktionen (Views, Likes & Kommentare)
Um die Datenintegrität relationaler Datenbanken (Foreign Key Constraints) über Servergrenzen hinweg zu wahren, werden Interaktionen intelligent geroutet:
* **Herkunfts-Erkennung:** Jedes Video besitzt eine eindeutige ID mit einem Server-Präfix (`app1_` oder `app2_`).
* **Lokale Interaktion:** Gehört das Video dem Server, auf dem der Nutzer sich befindet, wird die Interaktion direkt in die lokale PostgreSQL-Datenbank geschrieben.
* **Netzwerk-Tunneling:** Interagiert ein Nutzer mit einem "Fremd-Video", fängt das lokale Backend den Request ab, verweigert den lokalen Schreibzugriff (da das Video in der lokalen DB-Tabelle fehlt) und tunnelt den Call via HTTP-Post an das Backend des Ursprungsservers.
* **Branding:** Bei Kommentaren wird der Herkunftsort automatisch im Text verewigt (z. B. `[Kommentartext] (via App 1)`), sodass im Feed sofort ersichtlich ist, dass dieser Inhalt von einer externen Plattform stammt.

---

## Features

* **Cross-Kompatibilität:** Nahtloser Austausch von Videos, Kommentaren und Likes zwischen unabhängigen Plattformen.
* **Dezentrales Kollektiv:** Stärkung kleinerer Plattformen durch Vernetzung, um gemeinsam als Alternative zu großen Monopolen aufzutreten.
* **Responsive Design:** Die Benutzeroberfläche ist sowohl für Desktop- als auch für Mobilgeräte optimiert.
* **PWA-Kompatibilität:** Die Webseiten lassen sich als Progressive Web Apps direkt auf dem Endgerät installieren.
