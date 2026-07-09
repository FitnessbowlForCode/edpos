import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import boto3
import httpx
from botocore.client import Config
from botocore.exceptions import ClientError
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

# ==========================================
# INITIALISIERUNG & MIDDLEWARE
# ==========================================

app = FastAPI(root_path="/api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

s3_client = boto3.client(
    "s3",
    endpoint_url=os.getenv("S3_ENDPOINT"),
    aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
    aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
    config=Config(signature_version="s3v4"),
)

BUCKET_NAME = os.getenv("S3_BUCKET", "bucket1")
PUBLIC_IP = os.getenv("PUBLIC_SERVER_IP")
DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ==========================================
# DATENBANK MODELLE
# ==========================================


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)


class Video(Base):
    __tablename__ = "videos"

    id = Column(String, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    thumbnail_url = Column(String, nullable=True)
    playlist_url = Column(String, nullable=False)
    origin = Column(String, default="App 1")
    views = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    dislikes = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(
        String, ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    text = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# ==========================================
# STARTUP VALIDIERUNGEN
# ==========================================


def init_db():
    Base.metadata.create_all(bind=engine)
    print("INFO: PostgreSQL-Tabellen wurden ueberprueft/erstellt.")


def init_minio():
    try:
        s3_client.head_bucket(Bucket=BUCKET_NAME)
        print(f"INFO: Verbindung zu MinIO steht. Bucket '{BUCKET_NAME}' ist einsatzbereit.")
    except ClientError as e:
        print(f"CRITICAL ERROR: Das Bucket '{BUCKET_NAME}' wurde in MinIO nicht gefunden!")
        raise e


# ==========================================
# VIDEO CONVERSION & UPLOAD LOGIC (FFMPEG)
# ==========================================


def convert_and_upload_hls(
    file_path: Path, video_id: str, title: str, description: str
):
    output_dir = Path(f"/tmp/{video_id}")
    output_dir.mkdir(parents=True, exist_ok=True)

    hls_cmd = [
        "ffmpeg",
        "-i",
        str(file_path),
        "-filter_complex",
        "[0:v]split=3[v1][v2][v3];[v1]scale=w=640:h=360[v1out];[v2]scale=w=1280:h=720[v2out];[v3]scale=w=1920:h=1080[v3out]",
        "-c:v",
        "libx264",
        "-crf",
        "23",
        "-profile:v",
        "baseline",
        "-level",
        "3.0",
        "-c:a",
        "aac",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-map",
        "[v1out]",
        "-map",
        "0:a",
        "-map",
        "[v2out]",
        "-map",
        "0:a",
        "-map",
        "[v3out]",
        "-map",
        "0:a",
        "-f",
        "hls",
        "-hls_time",
        "4",
        "-hls_list_size",
        "0",
        "-var_stream_map",
        "v:0,a:0 v:1,a:1 v:2,a:2",
        "-hls_segment_filename",
        f"{output_dir}/v%v_seg_%03d.ts",
        "-master_pl_name",
        "master.m3u8",
        f"{output_dir}/v%v_playlist.m3u8",
    ]

    thumb_cmd = [
        "ffmpeg",
        "-ss",
        "00:00:01",
        "-i",
        str(file_path),
        "-vframes",
        "1",
        "-q:v",
        "2",
        str(output_dir / "thumbnail.jpg"),
    ]

    try:
        print("INFO: Generiere Multi-Res HLS-Streams und Thumbnail...")
        subprocess.run(hls_cmd, check=True)
        subprocess.run(thumb_cmd, check=True)

        for file in output_dir.glob("*"):
            s3_key = f"{video_id}/{file.name}"
            if file.suffix == ".jpg":
                content_type = "image/jpeg"
            elif "master.m3u8" in file.name or "playlist.m3u8" in file.name:
                content_type = "application/x-mpegURL"
            else:
                content_type = "video/MP2T"

            s3_client.upload_file(
                str(file),
                BUCKET_NAME,
                s3_key,
                ExtraArgs={"ContentType": content_type},
            )

        db = SessionLocal()
        try:
            playlist_url = f"https://{PUBLIC_IP}/stream/{BUCKET_NAME}/{video_id}/master.m3u8"
            thumbnail_url = f"https://{PUBLIC_IP}/stream/{BUCKET_NAME}/{video_id}/thumbnail.jpg"
            aktueller_origin = "App 1" if "app1" in PUBLIC_IP else "App 2"

            neues_video = Video(
                id=video_id,
                title=title,
                description=description,
                playlist_url=playlist_url,
                thumbnail_url=thumbnail_url,
                origin=aktueller_origin,
                views=0,
                likes=0,
                dislikes=0,
                created_at=datetime.utcnow(),
            )
            db.add(neues_video)
            db.commit()
            print(f"INFO: Video '{title}' erfolgreich registriert!")
        except Exception as db_err:
            print(f"DB Error: {db_err}")
        finally:
            db.close()

    except Exception as e:
        print(f"Error bei Konvertierung/Upload: {e}")
    finally:
        if output_dir.exists():
            shutil.rmtree(output_dir)
        if file_path.exists():
            file_path.unlink()


# ==========================================
# ENDPUNKTE (API ROUTES)
# ==========================================


@app.post("/upload")
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(...),
    description: str = Form(None),
):
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    clean_name = (
        os.path.splitext(file.filename)[0]
        .replace(" ", "_")
        .replace("(", "")
        .replace(")", "")
    )
    prefix = "app1" if "app1" in PUBLIC_IP else "app2"
    video_id = f"{prefix}_{clean_name}_{timestamp}"

    temp_file = Path(f"/tmp/{video_id}.mp4")

    with temp_file.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    background_tasks.add_task(
        convert_and_upload_hls, temp_file, video_id, title, description
    )

    return {
        "status": "Processing started",
        "video_id": video_id,
        "title": title,
        "message": "Das Video wird im Hintergrund konvertiert und registriert.",
    }


@app.get("/videos")
async def get_all_videos(request: Request, db: Session = Depends(get_db)):
    """Holt lokale Videos und fragt den Nachbarn ab, wenn die Anfrage vom Browser kommt."""
    lokale_videos = db.query(Video).order_by(Video.created_at.desc()).all()

    ergebnis_liste = []
    for v in lokale_videos:
        ergebnis_liste.append(
            {
                "id": v.id,
                "title": v.title,
                "description": v.description,
                "playlist_url": v.playlist_url,
                "thumbnail_url": v.thumbnail_url,
                "origin": v.origin,
                "views": v.views,
                "likes": v.likes,
                "dislikes": v.dislikes,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
        )

    is_federated_request = request.headers.get("X-Federation") == "True"
    nachbar_url = os.getenv("NEXT_NEIGHBOR_API")

    if nachbar_url and not is_federated_request:
        try:
            print(f"INFO: Foederations-Abfrage an: {nachbar_url}/videos")

            async with httpx.AsyncClient(verify=False) as client:
                response = await client.get(
                    f"{nachbar_url}/videos",
                    timeout=5.0,
                    headers={"X-Federation": "True"},
                )

                if response.status_code == 200:
                    nachbar_videos = response.json()
                    print(f"INFO: Erfolgreich {len(nachbar_videos)} Videos vom Nachbarn erhalten.")

                    for nv in nachbar_videos:
                        if nv["id"] not in [v["id"] for v in ergebnis_liste]:
                            ergebnis_liste.append(nv)

        except httpx.RequestError as exc:
            print(f"WARNUNG: Nachbar {nachbar_url} nicht erreichbar ({exc}).")
        except Exception as e:
            print(f"FEHLER bei Foederation: {e}")
    else:
        print("INFO: Reine lokale Ausgabe (Anfrage kam vom Nachbar-Server oder keine Nachbar-API definiert).")

    ergebnis_liste.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return ergebnis_liste


# ==========================================
# INTERAKTIONS-ENDPUNKTE (VIEWS, LIKES, DISLIKES)
# ==========================================


@app.post("/videos/{video_id}/view")
async def increment_view(video_id: str, db: Session = Depends(get_db)):
    wir_sind = "App 1" if "app1" in PUBLIC_IP else "App 2"
    video_stammt_von = "App 1" if "app1_" in video_id else "App 2"
    nachbar_url = os.getenv("NEXT_NEIGHBOR_API")

    if wir_sind == video_stammt_von:
        video = db.query(Video).filter(Video.id == video_id).first()
        if video:
            video.views += 1
            db.commit()
            return {"views": video.views}
    elif nachbar_url:
        try:
            async with httpx.AsyncClient(verify=False) as client:
                r = await client.post(f"{nachbar_url}/videos/{video_id}/view", timeout=2.0)
                return r.json()
        except Exception:
            pass
    return {"error": "Video nicht gefunden"}, 404


@app.post("/videos/{video_id}/like")
async def increment_like(video_id: str, db: Session = Depends(get_db)):
    wir_sind = "App 1" if "app1" in PUBLIC_IP else "App 2"
    video_stammt_von = "App 1" if "app1_" in video_id else "App 2"
    nachbar_url = os.getenv("NEXT_NEIGHBOR_API")

    if wir_sind == video_stammt_von:
        video = db.query(Video).filter(Video.id == video_id).first()
        if video:
            video.likes += 1
            db.commit()
            return {"likes": video.likes}
    elif nachbar_url:
        try:
            async with httpx.AsyncClient(verify=False) as client:
                r = await client.post(f"{nachbar_url}/videos/{video_id}/like", timeout=2.0)
                return r.json()
        except Exception:
            pass
    return {"error": "Video nicht gefunden"}, 404


@app.post("/videos/{video_id}/dislike")
async def increment_dislike(video_id: str, db: Session = Depends(get_db)):
    wir_sind = "App 1" if "app1" in PUBLIC_IP else "App 2"
    video_stammt_von = "App 1" if "app1_" in video_id else "App 2"
    nachbar_url = os.getenv("NEXT_NEIGHBOR_API")

    if wir_sind == video_stammt_von:
        video = db.query(Video).filter(Video.id == video_id).first()
        if video:
            video.dislikes += 1
            db.commit()
            return {"dislikes": video.dislikes}
    elif nachbar_url:
        try:
            async with httpx.AsyncClient(verify=False) as client:
                r = await client.post(f"{nachbar_url}/videos/{video_id}/dislike", timeout=2.0)
                return r.json()
        except Exception:
            pass
    return {"error": "Video nicht gefunden"}, 404


# ==========================================
# INTERAKTIONS-ENDPUNKTE (COMMENTS)
# ==========================================


@app.post("/videos/{video_id}/comments")
async def add_comment(
    video_id: str, text: str = Form(...), db: Session = Depends(get_db)
):
    """Speichert den Kommentar lokal oder leitet ihn an den Nachbarn weiter."""
    wir_sind = "App 1" if "app1" in PUBLIC_IP else "App 2"
    video_stammt_von = "App 1" if "app1_" in video_id else "App 2"
    nachbar_url = os.getenv("NEXT_NEIGHBOR_API")

    if wir_sind == video_stammt_von:
        neuer_kommentar = Comment(video_id=video_id, text=text)
        db.add(neuer_kommentar)
        db.commit()
        return {"message": "Kommentar erfolgreich lokal hinzugefuegt"}

    elif nachbar_url:
        try:
            print(f"INFO: Leite Kommentar fuer {video_id} weiter an Nachbar: {nachbar_url}")
            markierter_text = f"{text} (via {wir_sind})"

            async with httpx.AsyncClient(verify=False) as client:
                response = await client.post(
                    f"{nachbar_url}/videos/{video_id}/comments",
                    data={"text": markierter_text},
                    timeout=3.0,
                )
                if response.status_code == 200:
                    return {"message": f"Kommentar erfolgreich an {nachbar_url} weitergeleitet"}
        except Exception as e:
            print(f"FEHLER beim Weiterleiten des Kommentars: {e}")

    return {"error": "Video-Herkunft unbekannt oder Nachbar offline"}, 400


@app.get("/videos/{video_id}/comments")
async def get_comments(video_id: str, db: Session = Depends(get_db)):
    """Holt die Kommentare lokal oder fragt den Nachbarn, falls das Video ihm gehoert."""
    wir_sind = "App 1" if "app1" in PUBLIC_IP else "App 2"
    video_stammt_von = "App 1" if "app1_" in video_id else "App 2"
    nachbar_url = os.getenv("NEXT_NEIGHBOR_API")

    if wir_sind == video_stammt_von:
        return (
            db.query(Comment)
            .filter(Comment.video_id == video_id)
            .order_by(Comment.created_at.desc())
            .all()
        )
    elif nachbar_url:
        try:
            print(f"INFO: Hole Kommentare fuer Fremd-Video {video_id} live von Nachbar: {nachbar_url}")
            async with httpx.AsyncClient(verify=False) as client:
                response = await client.get(
                    f"{nachbar_url}/videos/{video_id}/comments", timeout=3.0
                )
                if response.status_code == 200:
                    return response.json()
        except Exception as e:
            print(f"FEHLER beim Abrufen der Fremd-Kommentare: {e}")

    return []


# ==========================================
# CENTRAL STARTUP EVENT
# ==========================================


@app.on_event("startup")
def startup_event():
    init_db()
    init_minio()