"""Read-only local operations snapshot for the research webserver."""

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends
from freqtrade.rpc.api_server.deps import get_config
from freqtrade.rpc.api_server.webserver_bgwork import ApiBG
from freqtrade.rpc.api_server.api_studio import data, storage

router = APIRouter()


def _size(path):
    total = 0
    count = 0
    for file in Path(path).rglob('*'):
        if file.is_file() and not file.is_symlink():
            total += file.stat().st_size
            count += 1
    return {'files': count, 'bytes': total}


def _jobs(folder, limit=20):
    results = []
    for file in sorted(Path(folder).glob('*/record.json'), key=lambda p: p.stat().st_mtime, reverse=True):
        if file.is_symlink() or file.parent.is_symlink():
            continue
        try:
            row = json.loads(file.read_text(encoding='utf-8'))
            results.append({'id': row.get('id'), 'strategy': row.get('strategy'),
                            'status': row.get('status'), 'created_at': row.get('created_at'),
                            'finished_at': row.get('finished_at'), 'error': row.get('error')})
        except (OSError, ValueError):
            results.append({'id': file.parent.name, 'status': 'unreadable'})
        if len(results) >= limit:
            break
    return results


def _flat_jobs(folder, limit=20):
    results = []
    for file in sorted(Path(folder).glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True):
        if file.is_symlink():
            continue
        try:
            row = json.loads(file.read_text(encoding='utf-8'))
            results.append({key: row.get(key) for key in ('id', 'status', 'created_at', 'finished_at', 'error')})
        except (OSError, ValueError):
            results.append({'id': file.stem, 'status': 'unreadable'})
        if len(results) >= limit:
            break
    return results


@router.get('/operations')
def operations(config=Depends(get_config)):
    now = datetime.now(timezone.utc)
    inventory = data(config)['files']
    market = []
    for pair in config['exchange']['pair_whitelist']:
        for kind in ('futures', 'mark', 'funding_rate'):
            matching = [row for row in inventory if row['pair'] == pair and row['type'] == kind and row.get('end')]
            latest = max((row['end'] for row in matching), default=None)
            market.append({'pair': pair, 'type': kind, 'latest_utc': latest,
                           'age_hours': (now - datetime.fromisoformat(latest)).total_seconds() / 3600 if latest else None,
                           'status': 'local_inventory_only'})
    private = storage(config)
    return {'checked_at': now.isoformat(), 'engine': 'Freqtrade 2026.9',
            'market': market, 'storage': {'research': _size(private), 'data': _size(config['datadir'])},
            'native_flags': {'analysis_running': bool(ApiBG.analysis_running),
                             'download_running': bool(ApiBG.download_data_running)},
            'jobs': {'data_repairs': _flat_jobs(private / 'data_quality' / 'jobs'),
                     'runs': _jobs(private / 'runs'), 'optimizations': _jobs(private / 'optimizations'),
                     'walk_forward': _jobs(private / 'walk_forward'),
                     'matrices': _jobs(private / 'matrices'),
                     'sensitivity': _jobs(private / 'sensitivity'),
                     'seed_experiments': _jobs(private / 'seed_experiments')},
            'note': 'Trạng thái tệp và cờ worker chỉ là ảnh chụp tại thời điểm đọc; không suy bot paper đang RUNNING từ API Online.'}
