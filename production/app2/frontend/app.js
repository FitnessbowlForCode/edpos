const BACKEND_URL = "/api";

document.addEventListener("DOMContentLoaded", () => {

    const urlParams = new URLSearchParams(window.location.search);
    const videoId = urlParams.get("v");

    if (videoId) {
        // Einzelansicht aktivieren
        showSingleVideo(videoId);
    } else {
        // Startseite / Feed aktivieren
        initStartPage();
    }
});



function initStartPage() {
    document.getElementById("uploadCard").style.display = "block";
    document.getElementById("feedCard").style.display = "block";
    document.getElementById("watchCard").style.display = "none";

    loadVideos();

    const uploadForm = document.getElementById("uploadForm");
    if (uploadForm) {
        uploadForm.removeEventListener("submit", handleVideoUpload);
        uploadForm.addEventListener("submit", handleVideoUpload);
    }
}

async function loadVideos() {
    const videoGrid = document.getElementById("videoGrid");
    if (!videoGrid) return;

    try {
        const response = await fetch(`${BACKEND_URL}/videos`);
        const videos = await response.json();

        if (videos.length === 0) {
            videoGrid.innerHTML = "<p>Noch keine Videos in der Datenbank vorhanden.</p>";
            return;
        }

        videoGrid.innerHTML = "";

        videos.forEach(video => {
            const card = document.createElement("div");
            card.className = "video-card";
            card.style.cursor = "pointer";


            card.onclick = () => {
                window.location.search = `?v=${video.id}`;
            };


            card.innerHTML = `
                <img src="${video.thumbnail_url || "https://images.placeholders.dev/?width=640&height=360&text=Kein+Bild&bgColor=%23000000&textColor=%23ffffff"}" 
                     style="width:100%; aspect-ratio:16/9; object-fit: cover; border-radius: 8px 8px 0 0; display: block; background: #000;">
                <div class="video-info" style="padding: 10px;">
                    <h4 class="video-title" style="margin: 0 0 5px 0;">${video.title}</h4>
                    <p class="video-desc" style="margin: 0 0 10px 0; color: #666; font-size: 13px;">${video.description || "Keine Beschreibung."}</p>
                    <div class="video-meta" style="display: flex; justify-content: space-between; align-items: center; font-size: 11px; color: #909090;">
                        <span>${video.views} Aufrufe</span>
                        <span class="badge ${video.origin === "App 2" ? "app2" : ""}">${video.origin}</span>
                    </div>
                </div>
            `;

            videoGrid.appendChild(card);
        });

    } catch (error) {
        console.error("Fehler beim Laden der Videos:", error);
        videoGrid.innerHTML = "<p style='color: red;'>Fehler beim Verbinden mit dem Backend.</p>";
    }
}



async function showSingleVideo(videoId) {
    // Oberflächen-Wechsel
    document.getElementById("uploadCard").style.display = "none";
    document.getElementById("feedCard").style.display = "none";
    document.getElementById("watchCard").style.display = "block";

    try {

        await fetch(`${BACKEND_URL}/videos/${videoId}/view`, { method: "POST" });


        const response = await fetch(`${BACKEND_URL}/videos`);
        const videos = await response.json();
        const video = videos.find(v => v.id === videoId);

        if (!video) {
            document.getElementById("singleVideoTitle").innerText = "Video nicht gefunden 404";
            return;
        }

        document.getElementById("singleVideoTitle").innerText = video.title;
        document.getElementById("singleVideoDesc").innerText = video.description || "Keine Beschreibung vorhanden.";
        document.getElementById("singleVideoMeta").innerText = `${video.views} Aufrufe • Registriert am ${new Date(video.created_at).toLocaleDateString()}`;

        document.getElementById("likeCount").innerText = video.likes;
        document.getElementById("dislikeCount").innerText = video.dislikes;

        const badge = document.getElementById("singleVideoOrigin");
        badge.innerText = video.origin;
        badge.className = `badge ${video.origin === "App 2" ? "app2" : ""}`;

        const likeBtn = document.getElementById("likeBtn");
        const dislikeBtn = document.getElementById("dislikeBtn");

        const newLikeBtn = likeBtn.cloneNode(true);
        const newDislikeBtn = dislikeBtn.cloneNode(true);
        likeBtn.parentNode.replaceChild(newLikeBtn, likeBtn);
        dislikeBtn.parentNode.replaceChild(newDislikeBtn, dislikeBtn);

        newLikeBtn.addEventListener("click", async () => {
            const res = await fetch(`${BACKEND_URL}/videos/${videoId}/like`, { method: "POST" });
            const data = await res.json();
            if (data.likes !== undefined) document.getElementById("likeCount").innerText = data.likes;
        });

        newDislikeBtn.addEventListener("click", async () => {
            const res = await fetch(`${BACKEND_URL}/videos/${videoId}/dislike`, { method: "POST" });
            const data = await res.json();
            if (data.dislikes !== undefined) document.getElementById("dislikeCount").innerText = data.dislikes;
        });

        const commentInput = document.getElementById("commentInput");
        const commentBtn = document.getElementById("commentBtn");
        const commentsList = document.getElementById("commentsList");

        async function loadComments() {
            try {
                const res = await fetch(`${BACKEND_URL}/videos/${videoId}/comments`);
                const comments = await res.json();

                if (comments.length === 0) {
                    commentsList.innerHTML = `<p style="color: #666; font-style: italic;">Noch keine Kommentare. Schreibe den ersten!</p>`;
                    return;
                }

                commentsList.innerHTML = "";
                comments.forEach(c => {
                    const div = document.createElement("div");
                    div.style.background = "#f9f9f9";
                    div.style.padding = "10px 15px";
                    div.style.borderRadius = "6px";
                    div.style.borderLeft = "4px solid #AB2346";

                    const dateStr = new Date(c.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

                    div.innerHTML = `
                        <div style="font-size: 11px; color: #909090; margin-bottom: 3px;">Anonymer Nutzer • ${dateStr} Uhr</div>
                        <div style="font-size: 14px; color: #111;">${c.text}</div>
                    `;
                    commentsList.appendChild(div);
                });
            } catch (err) {
                console.error("Fehler beim Laden der Kommentare:", err);
            }
        }


        loadComments();

        const newCommentBtn = commentBtn.cloneNode(true);
        commentBtn.parentNode.replaceChild(newCommentBtn, commentBtn);

        newCommentBtn.addEventListener("click", async () => {
            const text = commentInput.value.trim();
            if (!text) return;

            const formData = new FormData();
            formData.append("text", text);

            try {
                const res = await fetch(`${BACKEND_URL}/videos/${videoId}/comments`, {
                    method: "POST",
                    body: formData
                });

                if (res.ok) {
                    commentInput.value = "";
                    loadComments();
                }
            } catch (err) {
                console.error("Fehler beim Posten des Kommentars:", err);
            }
        });


        const videoElement = document.getElementById("singleVideoPlayer");
        initHlsPlayer(videoElement, video.playlist_url);

    } catch (error) {
        console.error("Fehler bei der Videoverarbeitung im Watch-Modus:", error);
    }
}


function initHlsPlayer(videoElement, streamUrl) {
    const qualitySelect = document.getElementById("qualitySelect");

    if (Hls.isSupported()) {
        const hls = new Hls();
        hls.loadSource(streamUrl);
        hls.attachMedia(videoElement);

        hls.on(Hls.Events.MANIFEST_PARSED, function () {
            videoElement.muted = false;
            videoElement.play().catch(err => console.log("Autoplay blockiert, warte auf Interaktion:", err));

            qualitySelect.innerHTML = '<option value="-1">Automatisch (Auto)</option>';

            hls.levels.forEach((level, index) => {
                const option = document.createElement("option");
                option.value = index;
                option.innerText = `${level.height}p`;
                qualitySelect.appendChild(option);
            });
        });


        qualitySelect.onchange = () => {
            const levelId = parseInt(qualitySelect.value);
            hls.currentLevel = levelId;
            console.log(`Qualität manuell geändert auf: ${levelId === -1 ? "Auto" : hls.levels[levelId].height + "p"}`);
        };

    } else if (videoElement.canPlayType("application/vnd.apple.mpegurl")) {

        videoElement.src = streamUrl;
        videoElement.muted = false;
        videoElement.play().catch(err => console.log("Autoplay blockiert:", err));
        qualitySelect.innerHTML = '<option value="-1">Vom Browser verwaltet (Safari)</option>';
    }
}


async function handleVideoUpload(e) {
    e.preventDefault();
    const submitBtn = document.getElementById("submitBtn");
    const statusMessage = document.getElementById("uploadStatus");
    const fileInput = document.getElementById("videoFile");
    const titleInput = document.getElementById("videoTitle");
    const descInput = document.getElementById("videoDesc");

    submitBtn.disabled = true;
    submitBtn.innerText = "Wird verarbeitet...";
    statusMessage.className = "status";
    statusMessage.style.display = "none";

    const formData = new FormData();
    formData.append("file", fileInput.files[0]);
    formData.append("title", titleInput.value);
    formData.append("description", descInput.value);

    try {
        const response = await fetch(`${BACKEND_URL}/upload`, { method: "POST", body: formData });
        const result = await response.json();

        if (response.ok) {
            statusMessage.className = "status success";
            statusMessage.innerText = "✓ " + result.message;
            document.getElementById("uploadForm").reset();
            setTimeout(initStartPage, 3000);
        } else {
            throw new Error(result.detail ? JSON.stringify(result.detail) : "Upload fehlgeschlagen");
        }
    } catch (error) {
        statusMessage.className = "status error";
        statusMessage.innerText = "🛑 Fehler: " + error.message;
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerText = "Upload starten";
    }
}

function toggleUploadForm() {
    const form = document.getElementById('uploadForm');
    const btn = document.getElementById('toggleUploadBtn');

    if (form.style.display === 'none') {
        form.style.display = 'block';
        btn.textContent = '-';
    } else {
        form.style.display = 'none';
        btn.textContent = '+';
    }
}