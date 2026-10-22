FROM freqtradeorg/freqtrade@sha256:9d67afb8eb5f4e1210f4fb067efcbd5e005bd4f1c27f6f3888b8b9fc7f9b5199
COPY --chown=ftuser:ftuser api_local_strategies.py /freqtrade/freqtrade/rpc/api_server/api_local_strategies.py
COPY --chown=ftuser:ftuser webserver.editor.py /freqtrade/freqtrade/rpc/api_server/webserver.py
LABEL local.extension="strategy-editor" local.engine="official-2026.9"

COPY --chown=ftuser:ftuser api_studio.py /freqtrade/freqtrade/rpc/api_server/api_studio.py
COPY --chown=ftuser:ftuser api_runs.py /freqtrade/freqtrade/rpc/api_server/api_runs.py
COPY --chown=ftuser:ftuser api_paper.py /freqtrade/freqtrade/rpc/api_server/api_paper.py
COPY --chown=ftuser:ftuser api_presets.py /freqtrade/freqtrade/rpc/api_server/api_presets.py
COPY --chown=ftuser:ftuser api_replay.py /freqtrade/freqtrade/rpc/api_server/api_replay.py
