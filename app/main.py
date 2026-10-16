from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data"))).expanduser().resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "studio.sqlite3"
COMFYUI_URL = os.getenv("COMFYUI_URL", "http://127.0.0.1:8188").rstrip("/")
AGNES_API_BASE = os.getenv("AGNES_API_BASE", "https://apihub.agnes-ai.com").rstrip("/")
AGNES_API_KEY = os.getenv("AGNES_API_KEY", "").strip()
AGNES_VIDEO_MODEL = os.getenv("AGNES_VIDEO_MODEL", "agnes-video-2.5")
DEFAULT_WIDTH = int(os.getenv("RENDER_WIDTH", "1080"))
DEFAULT_HEIGHT = int(os.getenv("RENDER_HEIGHT", "1920"))
DEFAULT_FPS = int(os.getenv("RENDER_FPS", "24"))

app = FastAPI(title="漫剧工坊 MVP", version="0.1.0", description="ComfyUI + Agnes 视频适配器 + FFmpeg 漫剧制作工作台")
app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")
app.mount("/media", StaticFiles(directory=DATA_DIR), name="media")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect_db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def init_db() -> None:
    with connect_db() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
              id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS shots (
              id TEXT PRIMARY KEY, project_id TEXT NOT NULL, shot_no INTEGER NOT NULL, title TEXT NOT NULL,
              scene TEXT NOT NULL DEFAULT '', image_prompt TEXT NOT NULL DEFAULT '', motion_prompt TEXT NOT NULL DEFAULT '',
              status TEXT NOT NULL DEFAULT 'draft', keyframe_asset_id TEXT, first_frame_asset_id TEXT,
              last_frame_asset_id TEXT, video_asset_id TEXT, created_at TEXT NOT NULL,
              FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS assets (
              id TEXT PRIMARY KEY, project_id TEXT NOT NULL, shot_id TEXT, asset_type TEXT NOT NULL,
              original_name TEXT NOT NULL, rel_path TEXT NOT NULL, mime_type TEXT NOT NULL DEFAULT 'application/octet-stream',
              prompt TEXT NOT NULL DEFAULT '', metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
              FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
              FOREIGN KEY(shot_id) REFERENCES shots(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY, project_id TEXT NOT NULL, shot_id TEXT, provider TEXT NOT NULL,
              external_id TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'queued',
              payload_json TEXT NOT NULL DEFAULT '{}', result_json TEXT NOT NULL DEFAULT '{}',
              error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
              FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_shots_project ON shots(project_id, shot_no);
            CREATE INDEX IF NOT EXISTS idx_assets_project ON assets(project_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_jobs_project ON jobs(project_id, created_at);
            """
        )


init_db()


def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def get_project(project_id: str) -> dict[str, Any]:
    with connect_db() as con:
        row = con.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "项目不存在")
    return dict(row)


def get_asset(asset_id: str) -> dict[str, Any]:
    with connect_db() as con:
        row = con.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "资产不存在")
    result = dict(row)
    abs_path = (DATA_DIR / result["rel_path"]).resolve()
    if DATA_DIR not in abs_path.parents and abs_path != DATA_DIR:
        raise HTTPException(400, "非法资产路径")
    result["abs_path"] = abs_path
    return result


def media_url(rel_path: str) -> str:
    return "/media/" + rel_path.replace(os.sep, "/")


def comfy_request(method: str, route: str, **kwargs: Any) -> requests.Response:
    try:
        response = requests.request(method, COMFYUI_URL + route, timeout=kwargs.pop("timeout", 45), **kwargs)
        response.raise_for_status()
        return response
    except requests.RequestException as exc:
        raise HTTPException(502, f"ComfyUI 请求失败：{exc}") from exc


def safe_child_path(parent: Path, name: str) -> Path:
    path = (parent / name).resolve()
    if parent.resolve() not in path.parents:
        raise HTTPException(400, "非法文件路径")
    return path


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""


class ShotCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    scene: str = ""
    image_prompt: str = ""
    motion_prompt: str = ""
    shot_no: int | None = None


class ShotPatch(BaseModel):
    title: str | None = None
    scene: str | None = None
    image_prompt: str | None = None
    motion_prompt: str | None = None
    status: str | None = None
    keyframe_asset_id: str | None = None
    first_frame_asset_id: str | None = None
    last_frame_asset_id: str | None = None
    video_asset_id: str | None = None
    shot_no: int | None = None


class ComfyRun(BaseModel):
    project_id: str
    shot_id: str | None = None
    workflow: dict[str, Any]
    mappings: dict[str, dict[str, str]] = Field(default_factory=dict)
    prompt: str = ""
    negative_prompt: str = ""
    seed: int | None = None
    width: int | None = None
    height: int | None = None


class AgnesVideoCreate(BaseModel):
    project_id: str
    shot_id: str | None = None
    prompt: str
    mode: str = "keyframe"
    first_frame: str | None = None
    last_frame: str | None = None
    seconds: int = Field(default=5, ge=4, le=12)
    size: str = "720P"
    aspect_ratio: str = "9:16"
    model: str | None = None


class RenderRequest(BaseModel):
    project_id: str
    video_asset_ids: list[str] = Field(min_length=1)
    frame_policy: str = "dedupe1"  # none | dedupe1 | boundary2
    width: int = Field(default=DEFAULT_WIDTH, ge=256, le=3840)
    height: int = Field(default=DEFAULT_HEIGHT, ge=256, le=3840)
    fps: int = Field(default=DEFAULT_FPS, ge=12, le=60)
    voice_asset_id: str | None = None
    bgm_asset_id: str | None = None
    bgm_db: float = Field(default=-18.0, ge=-60.0, le=0.0)
    subtitle_asset_id: str | None = None
    subtitle_style: str = "FontName=Microsoft YaHei,FontSize=22,Outline=2,Shadow=1,Alignment=2,MarginV=72"


def insert_job(project_id: str, shot_id: str | None, provider: str, external_id: str = "", status: str = "queued", payload: dict[str, Any] | None = None, result: dict[str, Any] | None = None, error: str = "") -> str:
    jid = str(uuid.uuid4())
    stamp = now_iso()
    with connect_db() as con:
        con.execute(
            "INSERT INTO jobs(id,project_id,shot_id,provider,external_id,status,payload_json,result_json,error,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (jid, project_id, shot_id, provider, external_id, status, json.dumps(payload or {}, ensure_ascii=False), json.dumps(result or {}, ensure_ascii=False), error, stamp, stamp),
        )
    return jid


def update_job(job_id: str, **fields: Any) -> None:
    fields["updated_at"] = now_iso()
    allowed = {"external_id", "status", "result_json", "error", "payload_json", "updated_at"}
    values = {k: (json.dumps(v, ensure_ascii=False) if k in {"result_json", "payload_json"} and not isinstance(v, str) else v) for k, v in fields.items() if k in allowed}
    if not values:
        return
    sql = ",".join(f"{k}=?" for k in values)
    with connect_db() as con:
        con.execute(f"UPDATE jobs SET {sql} WHERE id=?", [*values.values(), job_id])


def get_job(job_id: str) -> dict[str, Any]:
    with connect_db() as con:
        row = con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "任务不存在")
    data = dict(row)
    for key in ("payload_json", "result_json"):
        try:
            data[key.removesuffix("_json")] = json.loads(data.pop(key) or "{}")
        except json.JSONDecodeError:
            data[key.removesuffix("_json")] = {}
    return data


def ffprobe(path: Path) -> dict[str, Any]:
    if not shutil.which("ffprobe"):
        raise RuntimeError("没有找到 ffprobe。请安装 FFmpeg 并将 ffmpeg、ffprobe 加入 PATH。")
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError("ffprobe 读取视频失败：" + result.stderr[-1200:])
    return json.loads(result.stdout)


def get_video_frame_count(path: Path, fps_fallback: int) -> int:
    info = ffprobe(path)
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video":
            for field in ("nb_read_frames", "nb_frames"):
                value = stream.get(field)
                if value and value != "N/A":
                    return int(value)
    duration = float(info.get("format", {}).get("duration", 0) or 0)
    if duration <= 0:
        raise RuntimeError(f"无法确定视频帧数：{path.name}")
    return max(1, round(duration * fps_fallback))


def escape_filter_path(path: Path) -> str:
    # FFmpeg subtitles filter parser requires special escaping, especially for Windows drive colons.
    value = str(path.resolve()).replace("\\", "/")
    for old, new in [("\\", "\\\\"), (":", "\\:"), ("'", "\\'"), (",", "\\,"), ("[", "\\["), ("]", "\\]")]:
        value = value.replace(old, new)
    return value


def run_render(job_id: str, req: RenderRequest) -> None:
    work_dir = DATA_DIR / "projects" / req.project_id / "renders" / ("work_" + job_id[:8])
    work_dir.mkdir(parents=True, exist_ok=True)
    final_path = DATA_DIR / "projects" / req.project_id / "renders" / f"manju_{job_id[:8]}.mp4"
    try:
        update_job(job_id, status="running")
        videos: list[Path] = []
        for aid in req.video_asset_ids:
            asset = get_asset(aid)
            if asset["project_id"] != req.project_id:
                raise RuntimeError("某个视频资产不属于当前项目")
            if asset["asset_type"] not in {"video", "clip"} and asset["abs_path"].suffix.lower() not in {".mp4", ".mov", ".mkv", ".webm", ".m4v"}:
                raise RuntimeError(f"资产不是视频：{asset['original_name']}")
            videos.append(asset["abs_path"])
        if not shutil.which("ffmpeg"):
            raise RuntimeError("没有找到 ffmpeg。请安装 FFmpeg 并将 ffmpeg、ffprobe 加入 PATH。")
        if req.frame_policy not in {"none", "dedupe1", "boundary2"}:
            raise RuntimeError("frame_policy 只能是 none、dedupe1 或 boundary2")

        normalized: list[Path] = []
        counts: list[int] = []
        for i, source in enumerate(videos):
            norm = work_dir / f"norm_{i:03d}.mp4"
            vf = (
                f"scale={req.width}:{req.height}:force_original_aspect_ratio=decrease,"
                f"pad={req.width}:{req.height}:(ow-iw)/2:(oh-ih)/2,"
                f"fps={req.fps},setsar=1,format=yuv420p"
            )
            cmd = ["ffmpeg", "-y", "-i", str(source), "-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-movflags", "+faststart", str(norm)]
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            if p.returncode:
                raise RuntimeError(f"归一化视频失败（{source.name}）：{p.stderr[-1500:]}")
            normalized.append(norm)
            counts.append(get_video_frame_count(norm, req.fps))

        trimmed: list[Path] = []
        for i, norm in enumerate(normalized):
            start = 0
            end = counts[i]
            if req.frame_policy in {"dedupe1", "boundary2"} and i > 0:
                start = 1  # B[0] is the repeated bridge frame already present at the end of the previous shot.
            if req.frame_policy == "boundary2" and i < len(normalized) - 1:
                end = counts[i] - 2  # Keep through original frame N-3: remove the final two source frames.
            if end <= start:
                raise RuntimeError(f"镜头 {i + 1} 太短，无法按当前帧策略裁剪。")
            out = work_dir / f"trim_{i:03d}.mp4"
            cmd = ["ffmpeg", "-y", "-i", str(norm), "-vf", f"trim=start_frame={start}:end_frame={end},setpts=PTS-STARTPTS", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(req.fps), "-video_track_timescale", "90000", str(out)]
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            if p.returncode:
                raise RuntimeError(f"边界帧裁剪失败：{p.stderr[-1500:]}")
            trimmed.append(out)

        concat_list = work_dir / "concat.txt"
        concat_list.write_text("\n".join("file '" + p.as_posix().replace("'", "'\\''") + "'" for p in trimmed), encoding="utf-8")
        merged = work_dir / "merged.mp4"
        p = subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", "-movflags", "+faststart", str(merged)], capture_output=True, text=True, timeout=3600)
        if p.returncode:
            raise RuntimeError("视频拼接失败：" + p.stderr[-1500:])

        cmd: list[str] = ["ffmpeg", "-y", "-i", str(merged)]
        voice = get_asset(req.voice_asset_id) if req.voice_asset_id else None
        bgm = get_asset(req.bgm_asset_id) if req.bgm_asset_id else None
        subs = get_asset(req.subtitle_asset_id) if req.subtitle_asset_id else None
        for audio_asset in (voice, bgm):
            if audio_asset and audio_asset["project_id"] != req.project_id:
                raise RuntimeError("音频资产不属于当前项目")
            if audio_asset:
                cmd += ["-i", str(audio_asset["abs_path"])]
        filters: list[str] = []
        audio_labels: list[str] = []
        next_input = 1
        if voice:
            filters.append(f"[{next_input}:a]aresample=48000,volume=1.0[voice]")
            audio_labels.append("[voice]")
            next_input += 1
        if bgm:
            filters.append(f"[{next_input}:a]aresample=48000,volume={req.bgm_db}dB[bgm]")
            audio_labels.append("[bgm]")
            next_input += 1
        vf_arg = None
        if subs:
            if subs["project_id"] != req.project_id:
                raise RuntimeError("字幕资产不属于当前项目")
            if subs["abs_path"].suffix.lower() not in {".srt", ".ass", ".ssa", ".vtt"}:
                raise RuntimeError("字幕资产应为 SRT、ASS、SSA 或 VTT 文件")
            sub_path = escape_filter_path(subs["abs_path"])
            vf_arg = f"subtitles=filename='{sub_path}':force_style='{req.subtitle_style}'"
        if audio_labels:
            filters.append("".join(audio_labels) + f"amix=inputs={len(audio_labels)}:duration=longest:dropout_transition=2,alimiter=limit=0.95[aout]")
        if filters:
            cmd += ["-filter_complex", ";".join(filters)]
        if vf_arg:
            cmd += ["-vf", vf_arg]
        cmd += ["-map", "0:v:0"]
        if audio_labels:
            cmd += ["-map", "[aout]", "-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
        else:
            cmd += ["-an"]
        cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(req.fps), "-movflags", "+faststart", "-shortest", str(final_path)]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
        if p.returncode:
            raise RuntimeError("混音/字幕/导出失败：" + p.stderr[-2000:])

        aid = str(uuid.uuid4())
        rel = final_path.relative_to(DATA_DIR).as_posix()
        with connect_db() as con:
            con.execute(
                "INSERT INTO assets(id,project_id,shot_id,asset_type,original_name,rel_path,mime_type,prompt,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (aid, req.project_id, None, "render", final_path.name, rel, "video/mp4", "", json.dumps({"job_id": job_id, "frame_policy": req.frame_policy, "fps": req.fps, "width": req.width, "height": req.height}, ensure_ascii=False), now_iso()),
            )
        update_job(job_id, status="completed", result_json={"asset_id": aid, "url": media_url(rel), "path": rel, "frames_before_trim": counts, "frame_policy": req.frame_policy})
    except Exception as exc:
        update_job(job_id, status="failed", error=str(exc), result_json={"message": str(exc)})
    finally:
        # Leave work files for debugging by default; cleanup can be added after production acceptance.
        pass


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (BASE_DIR / "app" / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "app": "manju-studio-mvp", "comfyui_url": COMFYUI_URL, "agnes_api_configured": bool(AGNES_API_KEY), "ffmpeg": bool(shutil.which("ffmpeg")), "ffprobe": bool(shutil.which("ffprobe")), "data_dir": str(DATA_DIR)}


@app.get("/api/settings")
def settings() -> dict[str, Any]:
    return {"comfyui_url": COMFYUI_URL, "agnes_api_base": AGNES_API_BASE, "agnes_api_configured": bool(AGNES_API_KEY), "agnes_video_model": AGNES_VIDEO_MODEL, "render_width": DEFAULT_WIDTH, "render_height": DEFAULT_HEIGHT, "render_fps": DEFAULT_FPS, "tts_api_configured": bool(os.getenv("TTS_API_BASE", "").strip())}


@app.get("/api/projects")
def list_projects() -> list[dict[str, Any]]:
    with connect_db() as con:
        rows = con.execute("SELECT p.*, (SELECT COUNT(*) FROM shots s WHERE s.project_id=p.id) AS shot_count FROM projects p ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


@app.post("/api/projects")
def create_project(body: ProjectCreate) -> dict[str, Any]:
    pid = str(uuid.uuid4())
    with connect_db() as con:
        con.execute("INSERT INTO projects(id,name,description,created_at) VALUES(?,?,?,?)", (pid, body.name.strip(), body.description, now_iso()))
    (DATA_DIR / "projects" / pid / "assets").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "projects" / pid / "renders").mkdir(parents=True, exist_ok=True)
    return get_project(pid)


@app.get("/api/projects/{project_id}/shots")
def list_shots(project_id: str) -> list[dict[str, Any]]:
    get_project(project_id)
    with connect_db() as con:
        rows = con.execute("""SELECT s.*, a.rel_path AS keyframe_rel_path, v.rel_path AS video_rel_path
          FROM shots s LEFT JOIN assets a ON a.id=s.keyframe_asset_id LEFT JOIN assets v ON v.id=s.video_asset_id
          WHERE s.project_id=? ORDER BY s.shot_no, s.created_at""", (project_id,)).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["keyframe_url"] = media_url(d["keyframe_rel_path"]) if d.get("keyframe_rel_path") else None
        d["video_url"] = media_url(d["video_rel_path"]) if d.get("video_rel_path") else None
        result.append(d)
    return result


@app.post("/api/projects/{project_id}/shots")
def create_shot(project_id: str, body: ShotCreate) -> dict[str, Any]:
    get_project(project_id)
    sid = str(uuid.uuid4())
    with connect_db() as con:
        next_no = con.execute("SELECT COALESCE(MAX(shot_no),0)+1 FROM shots WHERE project_id=?", (project_id,)).fetchone()[0]
        shot_no = body.shot_no if body.shot_no is not None else next_no
        con.execute("INSERT INTO shots(id,project_id,shot_no,title,scene,image_prompt,motion_prompt,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)", (sid, project_id, shot_no, body.title, body.scene, body.image_prompt, body.motion_prompt, "draft", now_iso()))
        row = con.execute("SELECT * FROM shots WHERE id=?", (sid,)).fetchone()
    return dict(row)


@app.patch("/api/shots/{shot_id}")
def patch_shot(shot_id: str, body: ShotPatch) -> dict[str, Any]:
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(400, "没有要更新的字段")
    with connect_db() as con:
        old = con.execute("SELECT * FROM shots WHERE id=?", (shot_id,)).fetchone()
        if old is None:
            raise HTTPException(404, "镜头不存在")
        allowed_status = {"draft", "keyframe_ready", "video_queued", "video_ready", "approved", "needs_fix"}
        if "status" in data and data["status"] not in allowed_status:
            raise HTTPException(400, f"status 必须是 {', '.join(sorted(allowed_status))}")
        for key in ("keyframe_asset_id", "first_frame_asset_id", "last_frame_asset_id", "video_asset_id"):
            if data.get(key):
                asset_row = con.execute("SELECT project_id FROM assets WHERE id=?", (data[key],)).fetchone()
                if asset_row is None or asset_row["project_id"] != old["project_id"]:
                    raise HTTPException(400, f"{key} 必须引用同一项目中的资产")
        updates = ",".join(f"{key}=?" for key in data)
        con.execute(f"UPDATE shots SET {updates} WHERE id=?", [*data.values(), shot_id])
        row = con.execute("SELECT * FROM shots WHERE id=?", (shot_id,)).fetchone()
    return dict(row)


@app.get("/api/projects/{project_id}/assets")
def list_assets(project_id: str, asset_type: str | None = None) -> list[dict[str, Any]]:
    get_project(project_id)
    with connect_db() as con:
        if asset_type:
            rows = con.execute("SELECT * FROM assets WHERE project_id=? AND asset_type=? ORDER BY created_at DESC", (project_id, asset_type)).fetchall()
        else:
            rows = con.execute("SELECT * FROM assets WHERE project_id=? ORDER BY created_at DESC", (project_id,)).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["url"] = media_url(d["rel_path"])
        try:
            d["metadata"] = json.loads(d.pop("metadata_json") or "{}")
        except json.JSONDecodeError:
            d["metadata"] = {}
        result.append(d)
    return result


@app.post("/api/projects/{project_id}/assets")
async def upload_asset(project_id: str, file: UploadFile = File(...), asset_type: str = Form("auto"), shot_id: str | None = Form(None), prompt: str = Form("")) -> dict[str, Any]:
    get_project(project_id)
    if shot_id:
        with connect_db() as con:
            found = con.execute("SELECT project_id FROM shots WHERE id=?", (shot_id,)).fetchone()
        if found is None or found["project_id"] != project_id:
            raise HTTPException(400, "镜头不属于当前项目")
    original = Path(file.filename or "upload.bin").name
    ext = Path(original).suffix.lower()
    if ext not in {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".mkv", ".webm", ".m4v", ".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".srt", ".ass", ".ssa", ".vtt", ".json"}:
        raise HTTPException(415, "不支持该文件类型。支持图片、视频、音频、字幕和 JSON。")
    inferred = "image" if ext in {".png", ".jpg", ".jpeg", ".webp"} else "video" if ext in {".mp4", ".mov", ".mkv", ".webm", ".m4v"} else "audio" if ext in {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"} else "subtitle" if ext in {".srt", ".ass", ".ssa", ".vtt"} else "workflow"
    kind = inferred if asset_type == "auto" else asset_type
    valid_types = {"image", "video", "clip", "audio", "voice", "bgm", "subtitle", "workflow", "render"}
    if kind not in valid_types:
        raise HTTPException(400, f"asset_type 必须是 {', '.join(sorted(valid_types))}")
    aid = str(uuid.uuid4())
    folder = DATA_DIR / "projects" / project_id / "assets"
    folder.mkdir(parents=True, exist_ok=True)
    dest = safe_child_path(folder, aid + ext)
    size = 0
    with dest.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > 2 * 1024 * 1024 * 1024:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(413, "单个文件不能超过 2GB")
            out.write(chunk)
    rel = dest.relative_to(DATA_DIR).as_posix()
    with connect_db() as con:
        con.execute("INSERT INTO assets(id,project_id,shot_id,asset_type,original_name,rel_path,mime_type,prompt,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (aid, project_id, shot_id, kind, original, rel, file.content_type or "application/octet-stream", prompt, json.dumps({"bytes": size}, ensure_ascii=False), now_iso()))
    if shot_id and kind == "image":
        with connect_db() as con:
            con.execute("UPDATE shots SET keyframe_asset_id=?,status='keyframe_ready' WHERE id=?", (aid, shot_id))
    if shot_id and kind in {"video", "clip", "render"}:
        with connect_db() as con:
            con.execute("UPDATE shots SET video_asset_id=?,status='video_ready' WHERE id=?", (aid, shot_id))
    return {"id": aid, "project_id": project_id, "shot_id": shot_id, "asset_type": kind, "original_name": original, "rel_path": rel, "url": media_url(rel), "created_at": now_iso()}


@app.post("/api/comfyui/test")
def comfy_test() -> dict[str, Any]:
    response = comfy_request("GET", "/system_stats")
    return {"ok": True, "url": COMFYUI_URL, "system": response.json()}


@app.post("/api/comfyui/run")
def comfy_run(body: ComfyRun) -> dict[str, Any]:
    get_project(body.project_id)
    if body.shot_id:
        with connect_db() as con:
            row = con.execute("SELECT project_id FROM shots WHERE id=?", (body.shot_id,)).fetchone()
        if row is None or row["project_id"] != body.project_id:
            raise HTTPException(400, "镜头不属于当前项目")
    workflow = json.loads(json.dumps(body.workflow))
    values = {"prompt": body.prompt, "negative_prompt": body.negative_prompt, "seed": body.seed, "width": body.width, "height": body.height}
    for name, mapping in body.mappings.items():
        if name not in values or values[name] is None:
            continue
        node_id = mapping.get("node_id", "")
        field = mapping.get("field", "")
        if not node_id or not field or node_id not in workflow or "inputs" not in workflow[node_id] or field not in workflow[node_id]["inputs"]:
            raise HTTPException(400, f"ComfyUI 映射无效：{name} -> {node_id}.{field}")
        workflow[node_id]["inputs"][field] = values[name]
    resp = comfy_request("POST", "/prompt", json={"prompt": workflow})
    info = resp.json()
    external_id = info.get("prompt_id", "")
    if not external_id:
        raise HTTPException(502, f"ComfyUI 未返回 prompt_id：{info}")
    jid = insert_job(body.project_id, body.shot_id, "comfyui", external_id, "queued", {"prompt": body.prompt, "workflow": workflow})
    return {"job_id": jid, "prompt_id": external_id, "status": "queued"}


@app.get("/api/comfyui/jobs/{prompt_id}")
def comfy_job(prompt_id: str) -> dict[str, Any]:
    response = comfy_request("GET", f"/history/{prompt_id}")
    data = response.json()
    entry = data.get(prompt_id, {}) if isinstance(data, dict) else {}
    status = entry.get("status", {}) if isinstance(entry, dict) else {}
    completed = bool(status.get("completed")) if isinstance(status, dict) else False
    images: list[dict[str, Any]] = []
    outputs = entry.get("outputs", {}) if isinstance(entry, dict) else {}
    for node_id, output in outputs.items():
        for img in output.get("images", []):
            params = {"filename": img.get("filename", ""), "subfolder": img.get("subfolder", ""), "type": img.get("type", "output")}
            images.append({"node_id": node_id, **params, "url": "/api/comfyui/image?" + urlencode(params)})
    return {"prompt_id": prompt_id, "found": bool(entry), "completed": completed, "status": status, "images": images, "raw": entry if completed else {"status": status}}


@app.get("/api/comfyui/image")
def comfy_image(filename: str, subfolder: str = "", type: str = "output") -> Response:
    try:
        resp = requests.get(COMFYUI_URL + "/view", params={"filename": filename, "subfolder": subfolder, "type": type}, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(502, f"读取 ComfyUI 输出图失败：{exc}") from exc
    return Response(content=resp.content, media_type=resp.headers.get("content-type", "image/png"))


@app.post("/api/projects/{project_id}/import-comfy-image")
def import_comfy_image(project_id: str, filename: str, subfolder: str = "", type: str = "output", shot_id: str | None = None) -> dict[str, Any]:
    get_project(project_id)
    params = {"filename": filename, "subfolder": subfolder, "type": type}
    try:
        resp = requests.get(COMFYUI_URL + "/view", params=params, timeout=90)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(502, f"导入 ComfyUI 输出失败：{exc}") from exc
    ext = Path(filename).suffix.lower() or ".png"
    if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
        ext = ".png"
    aid = str(uuid.uuid4())
    folder = DATA_DIR / "projects" / project_id / "assets"
    folder.mkdir(parents=True, exist_ok=True)
    dest = safe_child_path(folder, aid + ext)
    dest.write_bytes(resp.content)
    rel = dest.relative_to(DATA_DIR).as_posix()
    with connect_db() as con:
        con.execute("INSERT INTO assets(id,project_id,shot_id,asset_type,original_name,rel_path,mime_type,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)", (aid, project_id, shot_id, "image", filename, rel, resp.headers.get("content-type", "image/png"), json.dumps({"source": "comfyui", "subfolder": subfolder}, ensure_ascii=False), now_iso()))
        if shot_id:
            con.execute("UPDATE shots SET keyframe_asset_id=?,status='keyframe_ready' WHERE id=? AND project_id=?", (aid, shot_id, project_id))
    return {"id": aid, "asset_type": "image", "original_name": filename, "url": media_url(rel)}


@app.post("/api/agnes/videos")
def agnes_create_video(body: AgnesVideoCreate) -> dict[str, Any]:
    get_project(body.project_id)
    if not AGNES_API_KEY:
        raise HTTPException(503, "尚未配置 AGNES_API_KEY。Pavo 网页可用不代表已开通 API；可先上传本地生成的视频资产。")
    if body.shot_id:
        with connect_db() as con:
            row = con.execute("SELECT project_id FROM shots WHERE id=?", (body.shot_id,)).fetchone()
        if row is None or row["project_id"] != body.project_id:
            raise HTTPException(400, "镜头不属于当前项目")
    if body.mode == "keyframe" and not (body.first_frame or body.last_frame):
        raise HTTPException(400, "关键帧模式至少需要 first_frame 或 last_frame")
    model = body.model or AGNES_VIDEO_MODEL
    payload: dict[str, Any] = {"model": model, "mode": body.mode, "prompt": body.prompt, "seconds": str(body.seconds), "size": body.size, "aspect_ratio": body.aspect_ratio}
    if body.first_frame:
        payload["first_frame"] = body.first_frame
    if body.last_frame:
        payload["last_frame"] = body.last_frame
    try:
        resp = requests.post(AGNES_API_BASE + "/v1/videos", headers={"Authorization": f"Bearer {AGNES_API_KEY}", "Content-Type": "application/json"}, json=payload, timeout=90)
        if resp.status_code >= 400:
            raise HTTPException(resp.status_code if resp.status_code < 500 else 502, f"Agnes API 返回错误：{resp.text[:1600]}")
        data = resp.json()
    except requests.RequestException as exc:
        raise HTTPException(502, f"Agnes API 请求失败：{exc}") from exc
    external_id = data.get("video_id") or data.get("task_id") or data.get("id") or ""
    jid = insert_job(body.project_id, body.shot_id, "agnes", external_id, "queued", payload, data)
    return {"job_id": jid, "external_id": external_id, "status": data.get("status", "queued"), "provider_response": data}


def recursive_video_url(data: Any) -> str | None:
    if isinstance(data, dict):
        for k in ("video_url", "url", "download_url"):
            v = data.get(k)
            if isinstance(v, str) and v.startswith(("http://", "https://")) and any(ext in v.lower() for ext in (".mp4", ".mov", ".webm", "video")):
                return v
        for v in data.values():
            found = recursive_video_url(v)
            if found:
                return found
    elif isinstance(data, list):
        for v in data:
            found = recursive_video_url(v)
            if found:
                return found
    return None


def recursive_status(data: Any) -> str:
    if isinstance(data, dict):
        for k in ("status", "state"):
            v = data.get(k)
            if isinstance(v, str) and v.lower() in {"queued", "pending", "running", "processing", "completed", "succeeded", "success", "failed", "error", "cancelled"}:
                return "completed" if v.lower() in {"completed", "succeeded", "success"} else "failed" if v.lower() in {"failed", "error", "cancelled"} else "running" if v.lower() in {"running", "processing"} else "queued"
        for v in data.values():
            found = recursive_status(v)
            if found != "unknown":
                return found
    elif isinstance(data, list):
        for v in data:
            found = recursive_status(v)
            if found != "unknown":
                return found
    return "unknown"


@app.get("/api/agnes/jobs/{job_id}")
def agnes_poll(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    if job["provider"] != "agnes":
        raise HTTPException(400, "该任务不是 Agnes 视频任务")
    if not AGNES_API_KEY:
        raise HTTPException(503, "未配置 Agnes API Key")
    external_id = job["external_id"]
    if not external_id:
        return job
    model = (job.get("payload") or {}).get("model", AGNES_VIDEO_MODEL)
    try:
        resp = requests.get(AGNES_API_BASE + "/agnesapi", params={"video_id": external_id, "model_name": model}, headers={"Authorization": f"Bearer {AGNES_API_KEY}"}, timeout=60)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        raise HTTPException(502, f"查询 Agnes 视频任务失败：{exc}") from exc
    status = recursive_status(data)
    url = recursive_video_url(data)
    if status != "unknown":
        update_job(job_id, status=status, result_json=data)
    if url:
        update_job(job_id, status="completed", result_json=data)
    return {"job_id": job_id, "external_id": external_id, "status": status, "video_url": url, "result": data}


@app.post("/api/render/concat")
def render_concat(body: RenderRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    get_project(body.project_id)
    if body.frame_policy not in {"none", "dedupe1", "boundary2"}:
        raise HTTPException(400, "frame_policy 只能是 none、dedupe1 或 boundary2")
    for asset_id in body.video_asset_ids:
        asset = get_asset(asset_id)
        if asset["project_id"] != body.project_id:
            raise HTTPException(400, "所有视频资产必须属于同一项目")
    for asset_id in (body.voice_asset_id, body.bgm_asset_id, body.subtitle_asset_id):
        if asset_id:
            asset = get_asset(asset_id)
            if asset["project_id"] != body.project_id:
                raise HTTPException(400, "音频/字幕资产必须属于同一项目")
    jid = insert_job(body.project_id, None, "ffmpeg_render", "", "queued", body.model_dump())
    background_tasks.add_task(run_render, jid, body)
    return {"job_id": jid, "status": "queued", "message": "渲染已加入本机后台任务。"}


@app.get("/api/jobs/{job_id}")
def poll_job(job_id: str) -> dict[str, Any]:
    return get_job(job_id)


@app.get("/api/projects/{project_id}/jobs")
def list_jobs(project_id: str) -> list[dict[str, Any]]:
    get_project(project_id)
    with connect_db() as con:
        rows = con.execute("SELECT * FROM jobs WHERE project_id=? ORDER BY created_at DESC LIMIT 100", (project_id,)).fetchall()
    output = []
    for row in rows:
        d = dict(row)
        for key in ("payload_json", "result_json"):
            try:
                d[key.removesuffix("_json")] = json.loads(d.pop(key) or "{}")
            except json.JSONDecodeError:
                d[key.removesuffix("_json")] = {}
        output.append(d)
    return output


@app.get("/api/media-file/{asset_id}")
def download_asset(asset_id: str) -> FileResponse:
    asset = get_asset(asset_id)
    return FileResponse(asset["abs_path"], filename=asset["original_name"], media_type=asset["mime_type"])
