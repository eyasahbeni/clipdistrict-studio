# ClipDistrict Studio — runs on Hugging Face Spaces (Docker), Railway, Render or any VPS.
FROM python:3.11-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Hugging Face runs containers as user 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=7860 \
    WHISPER_MODEL=base \
    CLIPDISTRICT_HOME=/home/user/workspace
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=user . .

EXPOSE 7860
# /data is the persistent disk on Hugging Face (if you add one); otherwise the workspace folder is used
CMD ["sh", "-c", "if [ -d /data ] && [ -w /data ]; then export CLIPDISTRICT_HOME=/data/clipdistrict; fi; python -m clipdistrict app --no-browser"]
