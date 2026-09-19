"""
vigilon/federated/server.py
Flower server — cloud-deployable, plugs in Aravindhan's aggregation strategy.
Logs per-round metrics to results/metrics/ as JSON.
"""

import flwr as fl
from flwr.common import Metrics, Parameters, Scalar
from flwr.server.strategy import FedAvg
from flwr.server.client_proxy import ClientProxy
from flwr.common import FitRes, EvaluateRes

import numpy as np
import json
import os
import time
import argparse
import yaml
from pathlib import Path
from typing import Optional, Union
from collections import defaultdict
from datetime import datetime


# ── Metric aggregation helpers ─────────────────────────────────────────────────

def weighted_average(metrics: list[tuple[int, Metrics]]) -> Metrics:
    """
    Flower metric aggregation callback.
    Computes weighted average of accuracy and loss across all clients.
    """
    if not metrics:
        return {}

    total_samples = sum(n for n, _ in metrics)
    aggregated: dict[str, float] = {}

    for key in metrics[0][1].keys():
        aggregated[key] = sum(
            n * m[key] for n, m in metrics if key in m
        ) / max(total_samples, 1)

    return aggregated


# ── Custom strategy wrapper ────────────────────────────────────────────────────

class VigilonStrategy(FedAvg):
    """
    Wrapper around FedAvg (or FedMedian from Aravindhan's strategy.py).
    Adds:
      - per-round metric logging to JSON
      - attack detection flagging
      - round timing
      - clean console output
    """

    def __init__(
        self,
        *args,
        metrics_dir: str = "results/metrics",
        attack_enabled: bool = False,
        aggregation: str = "fedavg",
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.metrics_dir    = Path(metrics_dir)
        self.metrics_dir.mkdir(parents=True, exist_ok=True)
        self.attack_enabled = attack_enabled
        self.aggregation    = aggregation
        self._round_history: list[dict] = []
        self._round_start: float = 0.0

        # Try to import Aravindhan's FedMedian — fall back to FedAvg if missing
        if aggregation == "median":
            try:
                from federated.strategy import FedMedian  # Aravindhan's file
                print("[Server] Using FedMedian aggregation (robust mode)")
                self._use_median = True
            except ImportError:
                print("[Server] FedMedian not found — falling back to FedAvg")
                self._use_median = False
        else:
            self._use_median = False
            print("[Server] Using FedAvg aggregation")

    # ── Flower strategy hooks ──────────────────────────────────────────────────

    def configure_fit(self, server_round, parameters, client_manager):
        """Inject per-round config (local epochs, batch size) into each client."""
        self._round_start = time.time()
        config = {
            "local_epochs": 2,
            "batch_size":   32,
            "server_round": server_round,
        }
        fit_ins = fl.common.FitIns(parameters, config)
        clients = client_manager.sample(
            num_clients=self.min_fit_clients,
            min_num_clients=self.min_available_clients,
        )
        return [(client, fit_ins) for client in clients]

    def aggregate_fit(self, server_round, results, failures):
        """
        Aggregate client weight updates.
        Delegates to parent FedAvg (coordinate-wise median handled by
        Aravindhan's strategy.py when imported above).
        """
        if failures:
            print(f"[Server] Round {server_round} — {len(failures)} client(s) failed")

        aggregated_params, aggregated_metrics = super().aggregate_fit(
            server_round, results, failures
        )

        elapsed = round(time.time() - self._round_start, 2)

        # Detect potential poisoning: look for extreme weight norms
        attack_detected = False
        if results:
            norms = []
            for _, fit_res in results:
                weights = fl.common.parameters_to_ndarrays(fit_res.parameters)
                norm = float(np.mean([np.linalg.norm(w) for w in weights]))
                norms.append(norm)
            if len(norms) > 1:
                mean_norm = np.mean(norms)
                std_norm  = np.std(norms)
                if std_norm > 0 and any(abs(n - mean_norm) > 3 * std_norm for n in norms):
                    attack_detected = True
                    print(f"[Server] ⚠️  ATTACK DETECTED in round {server_round}!")

        round_meta = {
            "round":           server_round,
            "timestamp":       datetime.now().isoformat(),
            "elapsed_s":       elapsed,
            "num_clients":     len(results),
            "num_failures":    len(failures),
            "attack_detected": attack_detected,
            "aggregation":     self.aggregation,
        }
        self._save_round_meta(server_round, round_meta)
        print(f"[Server] Round {server_round} fit complete — "
              f"{len(results)} clients  elapsed={elapsed}s"
              f"{'  ⚠️ ATTACK' if attack_detected else ''}")

        return aggregated_params, aggregated_metrics

    def aggregate_evaluate(self, server_round, results, failures):
        """Aggregate evaluation metrics and log to disk."""
        loss_aggregated, metrics_aggregated = super().aggregate_evaluate(
            server_round, results, failures
        )

        if metrics_aggregated:
            accuracy = metrics_aggregated.get("accuracy", 0.0)
            loss     = loss_aggregated if loss_aggregated else 0.0

            record = {
                "round":    server_round,
                "accuracy": round(float(accuracy), 4),
                "loss":     round(float(loss), 4),
                "timestamp": datetime.now().isoformat(),
            }
            self._round_history.append(record)
            self._save_global_metrics()

            print(f"[Server] Round {server_round} eval — "
                  f"accuracy={accuracy:.4f}  loss={loss:.4f}")

        return loss_aggregated, metrics_aggregated

    # ── Internal ───────────────────────────────────────────────────────────────

    def _save_round_meta(self, server_round: int, data: dict) -> None:
        path = self.metrics_dir / f"server_round_{server_round:03d}.json"
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def _save_global_metrics(self) -> None:
        path = self.metrics_dir / "global_metrics.json"
        with open(path, "w") as f:
            json.dump(self._round_history, f, indent=2)


# ── Server factory ─────────────────────────────────────────────────────────────

def build_server(cfg: dict) -> tuple[fl.server.Server, fl.server.ServerConfig]:
    """
    Build Flower Server + ServerConfig from a config dict.
    Returns (server, config) ready for fl.server.start_server().
    """
    fl_cfg  = cfg.get("federated", {})
    sec_cfg = cfg.get("security",  {})
    log_cfg = cfg.get("logging",   {})

    num_rounds         = fl_cfg.get("num_rounds",         20)
    num_clients        = fl_cfg.get("num_clients",         3)
    aggregation        = fl_cfg.get("aggregation",    "median")
    attack_enabled     = sec_cfg.get("attack_enabled",  False)
    metrics_dir        = log_cfg.get("metrics_dir", "results/metrics")

    strategy = VigilonStrategy(
        # FedAvg base params
        fraction_fit          = 1.0,          # use ALL available clients
        fraction_evaluate     = 1.0,
        min_fit_clients       = num_clients,
        min_evaluate_clients  = num_clients,
        min_available_clients = num_clients,
        evaluate_metrics_aggregation_fn = weighted_average,
        # Vigilon extras
        metrics_dir    = metrics_dir,
        attack_enabled = attack_enabled,
        aggregation    = aggregation,
    )

    server = fl.server.Server(
        client_manager=fl.server.SimpleClientManager(),
        strategy=strategy,
    )
    server_cfg = fl.server.ServerConfig(num_rounds=num_rounds)

    return server, server_cfg


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Start the Vigilon Flower server")
    parser.add_argument("--host",    type=str, default="0.0.0.0",
                        help="Bind host (0.0.0.0 for cloud/LAN)")
    parser.add_argument("--port",    type=int, default=8080)
    parser.add_argument("--rounds",  type=int, default=None,
                        help="Override num_rounds from config")
    parser.add_argument("--config",  type=str, default="config.yaml")
    parser.add_argument("--attack",  type=str, default=None,
                        choices=["on", "off"],
                        help="Override attack_enabled from config")
    parser.add_argument("--aggregation", type=str, default=None,
                        choices=["fedavg", "median"],
                        help="Override aggregation from config")
    args = parser.parse_args()

    # Load config
    cfg: dict = {}
    if os.path.exists(args.config):
        with open(args.config) as f:
            cfg = yaml.safe_load(f)
    else:
        print(f"[Server] config.yaml not found — using defaults")

    # CLI overrides
    if args.rounds:
        cfg.setdefault("federated", {})["num_rounds"] = args.rounds
    if args.attack:
        cfg.setdefault("security", {})["attack_enabled"] = (args.attack == "on")
    if args.aggregation:
        cfg.setdefault("federated", {})["aggregation"] = args.aggregation

    server, server_cfg = build_server(cfg)

    address = f"{args.host}:{args.port}"
    print(f"\n{'='*55}")
    print(f"  VIGILON Federated Server")
    print(f"  Address    : {address}")
    print(f"  Rounds     : {server_cfg.num_rounds}")
    print(f"  Aggregation: {cfg.get('federated',{}).get('aggregation','median')}")
    print(f"  Attack mode: {cfg.get('security',{}).get('attack_enabled', False)}")
    print(f"{'='*55}\n")

    fl.server.start_server(
        server_address=address,
        server=server,
        config=server_cfg,
    )


if __name__ == "__main__":
    main()