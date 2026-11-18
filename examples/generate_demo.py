"""Generate a 10-second original test recording and SRT using trusted local FFmpeg."""
from pathlib import Path
import subprocess
root = Path(__file__).resolve().parent
output = root / 'demo-clipdistrict.mp4'
if output.exists():
    print(f'Already exists: {output}')
else:
    subprocess.run([
        'ffmpeg','-nostdin','-hide_banner','-loglevel','error','-n',
        '-f','lavfi','-i','color=c=0x481f79:s=720x405:r=24:d=10',
        '-f','lavfi','-i','anullsrc=channel_layout=stereo:sample_rate=44100',
        '-t','10','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p',
        '-c:a','aac','-shortest','-movflags','+faststart',str(output)],
        check=True,timeout=90
    )
    print('Generated',output)
