from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List


@dataclass(slots=True)
class ContractEntry:
    contract: str
    rollover_at: date


class MoexContractResolver:
    """
    Resolve continuous-like MOEX symbols (e.g. SV1!, BR1!) to real contracts.
    Configurable via JSON to support manual/automatic rollover changes.
    """

    def __init__(self, config_path: str | None = None) -> None:
        self._logger = logging.getLogger(self.__class__.__name__)
        self._aliases: Dict[str, str] = {}
        self._rollover: Dict[str, List[ContractEntry]] = {}
        if config_path:
            self._load_config(config_path)

    def resolve_symbol(self, raw_symbol: str) -> str:
        """
        Input:  RUS:SV1! or SV1!
        Output: RUS:SVM2026 or SVM2026 (depending on configured front contract)
        """
        exchange = ""
        ticker = raw_symbol
        if ":" in raw_symbol:
            exchange, ticker = raw_symbol.split(":", 1)

        root = self._aliases.get(ticker, ticker)
        chain = self._rollover.get(root)
        if not chain:
            return raw_symbol

        today = date.today()
        selected = chain[-1].contract
        for entry in chain:
            if today <= entry.rollover_at:
                selected = entry.contract
                break

        resolved = f"{exchange}:{selected}" if exchange else selected
        if resolved != raw_symbol:
            self._logger.info("MOEX contract resolved: %s -> %s", raw_symbol, resolved)
        return resolved

    def _load_config(self, config_path: str) -> None:
        path = Path(config_path)
        if not path.exists():
            self._logger.warning("MOEX contract config not found: %s", config_path)
            return

        payload = json.loads(path.read_text(encoding="utf-8"))
        aliases = payload.get("aliases", {})
        rollover = payload.get("rollover", {})

        parsed_rollover: Dict[str, List[ContractEntry]] = {}
        for root, entries in rollover.items():
            parsed_entries: List[ContractEntry] = []
            for item in entries:
                parsed_entries.append(
                    ContractEntry(
                        contract=str(item["contract"]),
                        rollover_at=date.fromisoformat(str(item["rollover_at"])),
                    )
                )
            parsed_rollover[root] = sorted(parsed_entries, key=lambda x: x.rollover_at)

        self._aliases = {str(k): str(v) for k, v in aliases.items()}
        self._rollover = parsed_rollover

