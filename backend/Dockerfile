FROM freqtradeorg/freqtrade@sha256:9d67afb8eb5f4e1210f4fb067efcbd5e005bd4f1c27f6f3888b8b9fc7f9b5199
COPY --chown=ftuser:ftuser api_local_strategies.py /freqtrade/freqtrade/rpc/api_server/api_local_strategies.py
COPY --chown=ftuser:ftuser webserver.editor.py /freqtrade/freqtrade/rpc/api_server/webserver.py
LABEL local.extension="strategy-editor" local.engine="official-2026.9"

COPY --chown=ftuser:ftuser api_studio.py /freqtrade/freqtrade/rpc/api_server/api_studio.py
COPY --chown=ftuser:ftuser api_runs.py /freqtrade/freqtrade/rpc/api_server/api_runs.py
COPY --chown=ftuser:ftuser api_experiment_notes.py /freqtrade/freqtrade/rpc/api_server/api_experiment_notes.py
COPY --chown=ftuser:ftuser api_paper.py /freqtrade/freqtrade/rpc/api_server/api_paper.py
COPY --chown=ftuser:ftuser api_presets.py /freqtrade/freqtrade/rpc/api_server/api_presets.py
COPY --chown=ftuser:ftuser api_replay.py /freqtrade/freqtrade/rpc/api_server/api_replay.py
COPY --chown=ftuser:ftuser paper_history.py /freqtrade/freqtrade/rpc/api_server/paper_history.py
COPY --chown=ftuser:ftuser api_optimization.py /freqtrade/freqtrade/rpc/api_server/api_optimization.py
COPY --chown=ftuser:ftuser api_data_quality.py /freqtrade/freqtrade/rpc/api_server/api_data_quality.py
COPY --chown=ftuser:ftuser api_paper_reconcile.py /freqtrade/freqtrade/rpc/api_server/api_paper_reconcile.py
COPY --chown=ftuser:ftuser api_walk_forward.py /freqtrade/freqtrade/rpc/api_server/api_walk_forward.py
COPY --chown=ftuser:ftuser api_sensitivity.py /freqtrade/freqtrade/rpc/api_server/api_sensitivity.py
COPY --chown=ftuser:ftuser api_parameter_scope.py /freqtrade/freqtrade/rpc/api_server/api_parameter_scope.py
COPY --chown=ftuser:ftuser api_operations.py /freqtrade/freqtrade/rpc/api_server/api_operations.py
COPY --chown=ftuser:ftuser api_matrix.py /freqtrade/freqtrade/rpc/api_server/api_matrix.py
