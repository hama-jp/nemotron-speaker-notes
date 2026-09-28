"""CPU media preparation that can overlap GPU inference."""
import json
import subprocess
from pathlib import Path


def inspect_media(path):
    r = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries',
         'format=duration:stream=codec_type,codec_name,pix_fmt,width,height',
         '-of', 'json', str(path)], capture_output=True, text=True,
        timeout=30, check=True,
    )
    return json.loads(r.stdout)


def preview_video(source, target, info):
    """Keep compatible H.264 video bit-for-bit; transcode only when needed."""
    video = next(s for s in info['streams'] if s['codec_type'] == 'video')
    audio = next(s for s in info['streams'] if s['codec_type'] == 'audio')
    copy_video = (video.get('codec_name') == 'h264'
                  and video.get('pix_fmt') in {'yuv420p', 'yuvj420p'}
                  and video.get('width', 0) <= 1920
                  and video.get('height', 0) <= 1080)
    base = ['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', str(source),
            '-map', '0:v:0', '-map', '0:a:0']
    encode = ['-vf', "scale='min(1280,iw)':-2", '-c:v', 'libx264',
              '-pix_fmt', 'yuv420p', '-preset', 'ultrafast', '-crf', '24', '-threads', '4']
    aopts = ['-c:a', 'copy' if audio.get('codec_name') == 'aac' else 'aac']
    # Atomic publication prevents a player from opening an incomplete MP4.
    temp = Path(target).with_name('preview.part.mp4')
    try:
        try:
            subprocess.run(base + (['-c:v', 'copy'] if copy_video else encode)
                           + aopts + ['-movflags', '+faststart', str(temp)],
                           check=True, capture_output=True, timeout=1800)
            mode = 'video-copy' if copy_video else 'transcode'
        except subprocess.CalledProcessError:
            if not copy_video:
                raise
            subprocess.run(base + encode + ['-c:a', 'aac', '-movflags', '+faststart', str(temp)],
                           check=True, capture_output=True, timeout=1800)
            mode = 'transcode-fallback'
        temp.replace(target)
        return mode
    finally:
        temp.unlink(missing_ok=True)
