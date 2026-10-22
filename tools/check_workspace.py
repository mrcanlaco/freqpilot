"""Offline native schema/StrategyResolver validation. Does not instantiate an exchange or bot."""
import json
import logging
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from freqtrade.configuration.config_validation import validate_config_schema
from freqtrade.enums import RunMode
from freqtrade.resolvers import StrategyResolver


def check(folder=Path('/freqtrade/user_data'), startup_only=False):
    config = json.loads((folder / 'config.json').read_text(encoding='utf-8-sig'))
    if config.get('dry_run') is not True or config.get('exchange', {}).get('name') != 'binance':
        raise ValueError('paper Binance configuration required')
    if any(config['exchange'].get(k) for k in ('key', 'secret', 'password')):
        raise ValueError('exchange credentials are not allowed')
    if (config.get('trading_mode'), config.get('margin_mode'), config.get('stake_currency')) != ('futures', 'isolated', 'USDT'):
        raise ValueError('isolated USDT-M configuration required')
    selected = folder / 'strategies'
    names = sorted(p.stem for p in selected.glob('*.py') if not p.name.startswith('_'))
    if 'StarterFutures' not in names:
        raise ValueError('StarterFutures installation template is missing')
    if startup_only:
        names = ['StarterFutures']
    for name in names:
        candidate = deepcopy(config)
        candidate.update(strategy=name, strategy_path=str(selected), user_data_dir=folder,
                         runmode=RunMode.DRY_RUN, recursive_strategy_search=False)
        strategy = StrategyResolver.load_strategy(candidate)
        validate_config_schema(candidate)
        for side in ('long', 'short'):
            leverage = strategy.leverage(pair='BTC/USDT:USDT', current_time=datetime.now(timezone.utc),
                                         current_rate=100000, proposed_leverage=10, max_leverage=125,
                                         entry_tag=None, side=side)
            if leverage != 1:
                raise ValueError('installation strategies must use 1x: ' + name)
    return names


if __name__ == '__main__':
    logging.disable(logging.CRITICAL)
    parser = argparse.ArgumentParser()
    parser.add_argument('--startup-only', action='store_true')
    args = parser.parse_args()
    try:
        names = check(startup_only=args.startup_only)
    except Exception as error:
        raise SystemExit('Native workspace validation failed (' + type(error).__name__ + '). Review the local config and strategies; no service was started.') from None
    print('Native schema and StrategyResolver passed for ' + str(len(names)) + ' strategies, isolated 1x. No exchange/network or trading process started.')
