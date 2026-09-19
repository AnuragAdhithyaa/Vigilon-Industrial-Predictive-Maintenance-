"""
vigilon/federated/client.py
Flower NumPyClient — runs on each factory edge node.
Loads local data partition, trains the model, returns updated weights.
"""

import flwr as fl
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
import json
import os
import time
from pathlib import Path


# ── Inline 1D-CNN (so client.py is self-contained) ────────────────────────────
class CNN1D(nn.Module):
    """Lightweight 1D-CNN for bearing fault classification."""

    def __init__(self, num_classes: int = 4):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv1d(1, 32, kernel_size=64, stride=2, padding=32),
            nn.BatchNorm1d(32),
            nn.ReLU(),
            nn.MaxPool1d(2),
            nn.Conv1d(32, 64, kernel_size=32, stride=2, padding=16),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.MaxPool1d(2),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.LazyLinear(128),
            nn.ReLU(),
            nn.Dropout(0.5),
            nn.Linear(128, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.classifier(self.features(x))


# ── Helper utilities ───────────────────────────────────────────────────────────

def load_client_data(client_id: int, data_dir: str = "data/processed"):
    """
    Load pre-split numpy arrays for this client.
    Expects:  data/processed/client_{id}/X_train.npy
                               client_{id}/y_train.npy
                               client_{id}/X_test.npy
                               client_{id}/y_test.npy
    Falls back to random data when files are missing (demo/testing mode).
    """
    base = Path(data_dir) / f"client_{client_id}"

    if base.exists():
        X_train = np.load(base / "X_train.npy").astype(np.float32)
        y_train = np.load(base / "y_train.npy").astype(np.int64)
        X_test  = np.load(base / "X_test.npy").astype(np.float32)
        y_test  = np.load(base / "y_test.npy").astype(np.int64)
        print(f"[Client {client_id}] Loaded real data: "
              f"train={len(X_train)}, test={len(X_test)}")
    else:
        # ── DEMO fallback ──────────────────────────────────────────────────
        print(f"[Client {client_id}] Data not found — using synthetic demo data.")
        rng = np.random.default_rng(seed=client_id * 42)
        X_train = rng.standard_normal((800, 1, 1024)).astype(np.float32)
        y_train = rng.integers(0, 4, size=800).astype(np.int64)
        X_test  = rng.standard_normal((200, 1, 1024)).astype(np.float32)
        y_test  = rng.integers(0, 4, size=200).astype(np.int64)

    # Ensure shape is (N, 1, 1024)
    if X_train.ndim == 2:
        X_train = X_train[:, np.newaxis, :]
        X_test  = X_test[:, np.newaxis, :]

    train_ds = TensorDataset(torch.from_numpy(X_train), torch.from_numpy(y_train))
    test_ds  = TensorDataset(torch.from_numpy(X_test),  torch.from_numpy(y_test))
    return train_ds, test_ds


def get_weights(model: nn.Module) -> list[np.ndarray]:
    """Extract model parameters as a list of NumPy arrays."""
    return [val.cpu().numpy() for _, val in model.state_dict().items()]


def set_weights(model: nn.Module, weights: list[np.ndarray]) -> None:
    """Load a list of NumPy arrays back into the model."""
    params = zip(model.state_dict().keys(), weights)
    state_dict = {k: torch.tensor(v) for k, v in params}
    model.load_state_dict(state_dict, strict=True)


def local_train(
    model: nn.Module,
    train_ds: TensorDataset,
    epochs: int,
    batch_size: int,
    device: torch.device,
) -> tuple[float, int]:
    """
    Standard PyTorch training loop (no DP here — DP is optional extension).
    Returns (average_loss, num_samples).
    """
    loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    criterion = nn.CrossEntropyLoss()

    model.train()
    total_loss, total_samples = 0.0, 0

    for _ in range(epochs):
        for X_batch, y_batch in loader:
            X_batch, y_batch = X_batch.to(device), y_batch.to(device)
            optimizer.zero_grad()
            loss = criterion(model(X_batch), y_batch)
            loss.backward()
            optimizer.step()
            total_loss   += loss.item() * len(X_batch)
            total_samples += len(X_batch)

    avg_loss = total_loss / max(total_samples, 1)
    return avg_loss, total_samples


def local_evaluate(
    model: nn.Module,
    test_ds: TensorDataset,
    device: torch.device,
) -> tuple[float, float, int]:
    """
    Evaluate model on local test split.
    Returns (loss, accuracy, num_samples).
    """
    loader = DataLoader(test_ds, batch_size=64, shuffle=False)
    criterion = nn.CrossEntropyLoss()

    model.eval()
    total_loss, correct, total = 0.0, 0, 0

    with torch.no_grad():
        for X_batch, y_batch in loader:
            X_batch, y_batch = X_batch.to(device), y_batch.to(device)
            logits = model(X_batch)
            loss   = criterion(logits, y_batch)
            total_loss += loss.item() * len(X_batch)
            correct    += (logits.argmax(1) == y_batch).sum().item()
            total      += len(X_batch)

    return total_loss / max(total, 1), correct / max(total, 1), total


# ── Flower Client ──────────────────────────────────────────────────────────────

class VigilonClient(fl.client.NumPyClient):
    """
    Flower NumPyClient for one factory node.

    Parameters
    ----------
    client_id   : int   — factory index (0-based)
    local_epochs: int   — training epochs per FL round
    batch_size  : int   — local mini-batch size
    data_dir    : str   — path to pre-processed data splits
    metrics_dir : str   — where per-round metrics JSON files are saved
    """

    def __init__(
        self,
        client_id: int,
        local_epochs: int = 2,
        batch_size: int = 32,
        data_dir: str = "data/processed",
        metrics_dir: str = "results/metrics",
    ):
        self.client_id    = client_id
        self.local_epochs = local_epochs
        self.batch_size   = batch_size
        self.metrics_dir  = Path(metrics_dir)
        self.metrics_dir.mkdir(parents=True, exist_ok=True)

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model  = CNN1D(num_classes=4).to(self.device)

        # Warm up LazyLinear by doing one forward pass
        dummy = torch.zeros(1, 1, 1024, device=self.device)
        self.model(dummy)

        self.train_ds, self.test_ds = load_client_data(client_id, data_dir)
        self._round = 0

    # ── Flower API ─────────────────────────────────────────────────────────────

    def get_parameters(self, config: dict) -> list[np.ndarray]:
        """Return current model weights to the server."""
        return get_weights(self.model)

    def fit(
        self,
        parameters: list[np.ndarray],
        config: dict,
    ) -> tuple[list[np.ndarray], int, dict]:
        """
        1. Receive global weights from server.
        2. Run local training.
        3. Return updated weights + metrics.
        """
        self._round += 1
        set_weights(self.model, parameters)

        epochs     = int(config.get("local_epochs", self.local_epochs))
        batch_size = int(config.get("batch_size",   self.batch_size))

        t0 = time.time()
        train_loss, n_samples = local_train(
            self.model, self.train_ds, epochs, batch_size, self.device
        )
        elapsed = round(time.time() - t0, 2)

        metrics = {
            "client_id":  self.client_id,
            "round":      self._round,
            "train_loss": round(train_loss, 4),
            "n_samples":  n_samples,
            "elapsed_s":  elapsed,
        }
        self._save_metrics("fit", metrics)
        print(f"[Client {self.client_id}] Round {self._round} fit — "
              f"loss={train_loss:.4f}  samples={n_samples}  time={elapsed}s")

        return get_weights(self.model), n_samples, metrics

    def evaluate(
        self,
        parameters: list[np.ndarray],
        config: dict,
    ) -> tuple[float, int, dict]:
        """
        Evaluate the global model on local test data.
        Returns (loss, num_samples, metrics_dict).
        """
        set_weights(self.model, parameters)
        loss, accuracy, n_samples = local_evaluate(self.model, self.test_ds, self.device)

        metrics = {
            "client_id": self.client_id,
            "round":     self._round,
            "loss":      round(loss, 4),
            "accuracy":  round(accuracy, 4),
            "n_samples": n_samples,
        }
        self._save_metrics("eval", metrics)
        print(f"[Client {self.client_id}] Evaluate — "
              f"acc={accuracy:.4f}  loss={loss:.4f}")

        return loss, n_samples, metrics

    # ── Internal ───────────────────────────────────────────────────────────────

    def _save_metrics(self, tag: str, metrics: dict) -> None:
        path = self.metrics_dir / f"client_{self.client_id}_{tag}_r{self._round}.json"
        with open(path, "w") as f:
            json.dump(metrics, f, indent=2)


# ── Entry point (run this file directly to start one client) ──────────────────

def main():
    import argparse, yaml

    parser = argparse.ArgumentParser(description="Start a Vigilon Flower client")
    parser.add_argument("--client_id",  type=int, default=0)
    parser.add_argument("--server",     type=str, default="localhost:8080")
    parser.add_argument("--config",     type=str, default="config.yaml")
    args = parser.parse_args()

    cfg = {}
    if os.path.exists(args.config):
        with open(args.config) as f:
            cfg = yaml.safe_load(f)

    fl_cfg   = cfg.get("federated", {})
    data_cfg = cfg.get("data",      {})

    client = VigilonClient(
        client_id    = args.client_id,
        local_epochs = fl_cfg.get("local_epochs",    2),
        batch_size   = fl_cfg.get("local_batch_size", 32),
        data_dir     = "data/processed",
        metrics_dir  = cfg.get("logging", {}).get("metrics_dir", "results/metrics"),
    )

    fl.client.start_numpy_client(server_address=args.server, client=client)


if __name__ == "__main__":
    main()