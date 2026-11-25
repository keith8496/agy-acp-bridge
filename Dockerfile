FROM python:3.12-slim-trixie AS agy-installer

ENV HOME=/root
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl libstdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL https://antigravity.google/cli/install.sh -o /tmp/install-agy.sh \
    && bash /tmp/install-agy.sh --dir /opt/agy \
    && test -x /opt/agy/agy

FROM python:3.12-slim-trixie

ENV HOME=/home/bridge \
    PYTHONUNBUFFERED=1 \
    AGY_BIN=/usr/local/bin/agy \
    AGY_APPDATA_ROOT=/home/bridge/.gemini \
    AGY_PROFILES_DIR=/home/bridge/.agy-profiles \
    AGY_STATE_FILE=/var/lib/agy-bridge/profile-state.json \
    AGY_CWD=/home/bridge/work \
    AGY_HOOK_LOG=/home/bridge/work/hooks.log \
    AGY_BRIDGE_BIND=0.0.0.0 \
    AGY_BRIDGE_PORT=20130

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libstdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 bridge \
    && useradd --uid 10001 --gid bridge --create-home --home-dir "$HOME" bridge \
    && install -d -m 0700 -o bridge -g bridge "$AGY_APPDATA_ROOT" "$AGY_CWD" /var/lib/agy-bridge

WORKDIR /app
COPY --from=agy-installer /opt/agy/agy /usr/local/bin/agy
COPY bridge.py /app/bridge.py
COPY hooks/hooks.json hooks/deny_builtin.py /home/bridge/work/.agents/

USER bridge
EXPOSE 20130
CMD ["python3", "/app/bridge.py"]
