from __future__ import annotations

from dataclasses import asdict, dataclass
from textwrap import dedent, indent
from typing import Any


@dataclass(frozen=True)
class PyTorchFeatureBundle:
    feature_id: str
    variant: str
    title: str
    summary: str
    dependencies: list[str]
    files: dict[str, str]
    validation_steps: list[str]
    evidence_targets: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def pytorch_feature_catalog() -> list[dict[str, Any]]:
    return [
        {
            "feature_id": "project_scaffold",
            "title": "PyTorch project scaffolding",
            "variants": ["classification", "vision", "nlp"],
            "summary": "Generate a real PyTorch package layout instead of another notebook crime scene.",
        },
        {
            "feature_id": "dataset_dataloader",
            "title": "Dataset and DataLoader builder",
            "variants": ["tabular", "vision", "text"],
            "summary": "Wire datasets, transforms, and collate behavior with fewer accidental bottlenecks.",
        },
        {
            "feature_id": "training_loop",
            "title": "Training loop generator",
            "variants": ["basic", "amp"],
            "summary": "Generate forward, backward, optimizer, and validation loops without pretending loss.backward is architecture.",
        },
        {
            "feature_id": "distributed_training",
            "title": "Distributed training setup",
            "variants": ["ddp", "accelerate", "deepspeed"],
            "summary": "Start DDP and launcher-aware training paths without improvising rank logic badly.",
        },
        {
            "feature_id": "checkpoint_resume",
            "title": "Checkpoint and resume guardrails",
            "variants": ["single_gpu", "distributed"],
            "summary": "Save model, optimizer, and scaler state like reproducibility matters because it does.",
        },
        {
            "feature_id": "profiler_observability",
            "title": "Profiler and training observability",
            "variants": ["default"],
            "summary": "Collect torch.profiler and TensorBoard evidence instead of performance folklore.",
        },
        {
            "feature_id": "export_inference",
            "title": "Export and inference deployment",
            "variants": ["torchscript_onnx"],
            "summary": "Validate TorchScript and ONNX export paths before calling a model deployable.",
        },
        {
            "feature_id": "peft_finetuning",
            "title": "PEFT and LoRA fine-tuning",
            "variants": ["lora_transformer"],
            "summary": "Start adapter-based fine-tuning with explicit trainable-parameter and merge checks.",
        },
    ]


def get_pytorch_feature_catalog_entry(feature_id: str) -> dict[str, Any]:
    normalized_feature = str(feature_id or "").strip().lower()
    for entry in pytorch_feature_catalog():
        if entry["feature_id"] == normalized_feature:
            return dict(entry)
    raise ValueError(f"Unknown PyTorch feature bundle `{feature_id}`.")


def generate_pytorch_feature_bundle(feature_id: str, *, variant: str | None = None) -> dict[str, Any]:
    normalized_feature = str(feature_id or "").strip().lower()
    normalized_variant = str(variant or "").strip().lower() or _default_variant(normalized_feature)
    bundle = _bundle_dispatch(normalized_feature, normalized_variant)
    return bundle.to_dict()


def _default_variant(feature_id: str) -> str:
    defaults = {
        "project_scaffold": "classification",
        "dataset_dataloader": "tabular",
        "training_loop": "basic",
        "distributed_training": "ddp",
        "checkpoint_resume": "single_gpu",
        "profiler_observability": "default",
        "export_inference": "torchscript_onnx",
        "peft_finetuning": "lora_transformer",
    }
    return defaults[feature_id]


def _bundle_dispatch(feature_id: str, variant: str) -> PyTorchFeatureBundle:
    builders = {
        "project_scaffold": _project_scaffold_bundle,
        "dataset_dataloader": _dataset_dataloader_bundle,
        "training_loop": _training_loop_bundle,
        "distributed_training": _distributed_training_bundle,
        "checkpoint_resume": _checkpoint_resume_bundle,
        "profiler_observability": _profiler_observability_bundle,
        "export_inference": _export_inference_bundle,
        "peft_finetuning": _peft_finetuning_bundle,
    }
    if feature_id not in builders:
        raise ValueError(f"Unknown PyTorch feature bundle `{feature_id}`.")
    return builders[feature_id](variant)


def _bundle(
    feature_id: str,
    variant: str,
    title: str,
    summary: str,
    dependencies: list[str],
    files: dict[str, str],
    validation_steps: list[str],
    evidence_targets: list[str],
) -> PyTorchFeatureBundle:
    return PyTorchFeatureBundle(
        feature_id=feature_id,
        variant=variant,
        title=title,
        summary=summary,
        dependencies=dependencies,
        files={path: dedent(content).strip() + "\n" for path, content in files.items()},
        validation_steps=validation_steps,
        evidence_targets=evidence_targets,
    )


def _project_scaffold_bundle(variant: str) -> PyTorchFeatureBundle:
    if variant not in {"classification", "vision", "nlp"}:
        raise ValueError(f"Unsupported PyTorch scaffold variant `{variant}`.")
    model_content = {
        "classification": dedent(
            """
            import torch

            from .config import hidden_dim, num_classes


            class DemoModel(torch.nn.Module):
                def __init__(self) -> None:
                    super().__init__()
                    self.encoder = torch.nn.Linear(128, hidden_dim)
                    self.head = torch.nn.Linear(hidden_dim, num_classes)

                def forward(self, inputs: torch.Tensor) -> torch.Tensor:
                    features = torch.relu(self.encoder(inputs))
                    return self.head(features)


            def build_loss():
                return torch.nn.CrossEntropyLoss()
            """
        ).strip(),
        "vision": dedent(
            """
            import torch

            from .config import num_classes


            class DemoModel(torch.nn.Module):
                def __init__(self) -> None:
                    super().__init__()
                    self.encoder = torch.nn.Sequential(
                        torch.nn.Conv2d(3, 16, kernel_size=3, stride=2, padding=1),
                        torch.nn.ReLU(),
                        torch.nn.Conv2d(16, 32, kernel_size=3, stride=2, padding=1),
                        torch.nn.ReLU(),
                        torch.nn.AdaptiveAvgPool2d((1, 1)),
                    )
                    self.head = torch.nn.Linear(32, num_classes)

                def forward(self, inputs: torch.Tensor) -> torch.Tensor:
                    features = self.encoder(inputs).flatten(1)
                    return self.head(features)


            def build_loss():
                return torch.nn.CrossEntropyLoss()
            """
        ).strip(),
        "nlp": dedent(
            """
            import torch

            from .config import hidden_dim, num_classes, vocab_size


            class DemoModel(torch.nn.Module):
                def __init__(self) -> None:
                    super().__init__()
                    self.embedding = torch.nn.Embedding(vocab_size, hidden_dim)
                    self.head = torch.nn.Linear(hidden_dim, num_classes)

                def forward(self, inputs: torch.Tensor) -> torch.Tensor:
                    features = self.embedding(inputs).mean(dim=1)
                    return self.head(features)


            def build_loss():
                return torch.nn.CrossEntropyLoss()
            """
        ).strip(),
    }[variant]
    data_content = {
        "classification": dedent(
            """
            import torch
            from torch.utils.data import DataLoader, TensorDataset

            from .config import batch_size


            def build_dataloaders():
                features = torch.zeros((128, 128), dtype=torch.float32)
                labels = torch.zeros((128,), dtype=torch.long)
                dataset = TensorDataset(features, labels)
                train_loader = DataLoader(dataset, batch_size=batch_size, shuffle=True, num_workers=2, pin_memory=True)
                val_loader = DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=2)
                return train_loader, val_loader
            """
        ).strip(),
        "vision": dedent(
            """
            import torch
            from torch.utils.data import DataLoader, TensorDataset

            from .config import batch_size


            def build_dataloaders():
                images = torch.zeros((128, 3, 64, 64), dtype=torch.float32)
                labels = torch.zeros((128,), dtype=torch.long)
                dataset = TensorDataset(images, labels)
                train_loader = DataLoader(dataset, batch_size=batch_size, shuffle=True, num_workers=2, pin_memory=True)
                val_loader = DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=2)
                return train_loader, val_loader
            """
        ).strip(),
        "nlp": dedent(
            """
            import torch
            from torch.utils.data import DataLoader, TensorDataset

            from .config import batch_size, vocab_size


            def build_dataloaders():
                tokens = torch.zeros((128, 32), dtype=torch.long)
                labels = torch.zeros((128,), dtype=torch.long)
                tokens[:, 0] = torch.arange(128) % max(vocab_size, 1)
                dataset = TensorDataset(tokens, labels)
                train_loader = DataLoader(dataset, batch_size=batch_size, shuffle=True, num_workers=2, pin_memory=True)
                val_loader = DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=2)
                return train_loader, val_loader
            """
        ).strip(),
    }[variant]
    return _bundle(
        "project_scaffold",
        variant,
        f"PyTorch {variant.replace('_', ' ')} starter",
        "A clean PyTorch package layout with separate config, model, data, and training entry points.",
        ["torch", "torchvision" if variant == "vision" else "numpy"],
        {
            "pytorch_starters/config.py": """
                batch_size = 32
                learning_rate = 3e-4
                epochs = 5
                hidden_dim = 256
                num_classes = 4
                vocab_size = 32000
            """,
            "pytorch_starters/model.py": model_content,
            "pytorch_starters/train.py": """
                from pathlib import Path

                import torch

                from .config import epochs, learning_rate
                from .data import build_dataloaders
                from .model import DemoModel, build_loss


                def main() -> None:
                    train_loader, val_loader = build_dataloaders()
                    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
                    model = DemoModel().to(device)
                    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
                    criterion = build_loss()
                    for epoch in range(epochs):
                        model.train()
                        for features, labels in train_loader:
                            features = features.to(device)
                            labels = labels.to(device)
                            optimizer.zero_grad(set_to_none=True)
                            logits = model(features)
                            loss = criterion(logits, labels)
                            loss.backward()
                            optimizer.step()
                        model.eval()
                        with torch.no_grad():
                            for features, labels in val_loader:
                                features = features.to(device)
                                labels = labels.to(device)
                                criterion(model(features), labels)
                    Path("artifacts").mkdir(parents=True, exist_ok=True)
                    torch.save({"model": model.state_dict(), "optimizer": optimizer.state_dict()}, "artifacts/checkpoint.pt")


                if __name__ == "__main__":
                    main()
            """,
            "pytorch_starters/data.py": data_content,
        },
        [
            "python -m pytorch_starters.train",
            "Verify artifacts/checkpoint.pt exists after training.",
            "Run one forward/backward smoke pass before trusting the starter.",
        ],
        [
        "Capture device, precision, batch size, and checkpoint artifact path.",
            "Record whether both the training loop and validation loop actually executed.",
        ],
    )


def _dataset_dataloader_bundle(variant: str) -> PyTorchFeatureBundle:
    if variant not in {"tabular", "vision", "text"}:
        raise ValueError(f"Unsupported DataLoader variant `{variant}`.")
    dataset_prelude = {
        "tabular": "",
        "vision": "import torchvision",
        "text": "from transformers import AutoTokenizer",
    }[variant]
    dataset_init = {
        "tabular": "pass",
        "vision": "pass",
        "text": "self.tokenizer = AutoTokenizer.from_pretrained(\"distilbert-base-uncased\")",
    }[variant]
    sample_block = {
        "tabular": dedent(
            """
            features = torch.zeros(32, dtype=torch.float32)
            return features, torch.tensor(index % 2, dtype=torch.long)
            """
        ).strip(),
        "vision": dedent(
            """
            transform = torchvision.transforms.Compose([
                torchvision.transforms.Resize((224, 224)),
                torchvision.transforms.ConvertImageDtype(torch.float32),
            ])
            image = torch.zeros((3, 256, 256), dtype=torch.uint8)
            return transform(image), torch.tensor(index % 10, dtype=torch.long)
            """
        ).strip(),
        "text": dedent(
            """
            tokens = self.tokenizer(
                f"sample text {index}",
                truncation=True,
                padding="max_length",
                max_length=32,
                return_tensors="pt",
            )
            return tokens["input_ids"].squeeze(0), torch.tensor(index % 2, dtype=torch.long)
            """
        ).strip(),
    }[variant]
    dataset_prelude_block = indent(dataset_prelude, "                ") + "\n" if dataset_prelude else ""
    dataset_init_block = indent(dataset_init, "                        ")
    sample_block_indented = indent(sample_block, "                        ")
    return _bundle(
        "dataset_dataloader",
        variant,
        f"PyTorch {variant} dataloader starter",
        "Generate dataset and DataLoader wiring with explicit batching, workers, and collate behavior.",
        ["torch", "pandas" if variant == "tabular" else "transformers" if variant == "text" else "torchvision"],
        {
            "pytorch_starters/dataloader.py": f"""
                import torch
                from torch.utils.data import DataLoader, Dataset
{dataset_prelude_block}


                class DemoDataset(Dataset):
                    def __init__(self) -> None:
{dataset_init_block}

                    def __len__(self) -> int:
                        return 1024

                    def __getitem__(self, index: int):
{sample_block_indented}


                def build_dataloader() -> DataLoader:
                    return DataLoader(
                        DemoDataset(),
                        batch_size=32,
                        shuffle=True,
                        num_workers=4,
                        pin_memory=True,
                        persistent_workers=True,
                    )
            """,
        },
        [
            "Run one batch through the dataloader and confirm shapes and dtypes.",
            "Measure worker count, pinned memory, and any custom collate behavior.",
        ],
        [
            "Show one batch shape and dtype summary.",
            "Record worker count and whether dataloader startup is a bottleneck.",
        ],
    )


def _training_loop_bundle(variant: str) -> PyTorchFeatureBundle:
    if variant not in {"basic", "amp"}:
        raise ValueError(f"Unsupported training loop variant `{variant}`.")
    training_loop_content = (
        dedent(
            """
            import torch


            def run_epoch(model, loader, optimizer, criterion, device):
                model.train()
                model.to(device)
                scaler = torch.cuda.amp.GradScaler(enabled=device.type == "cuda")
                for features, labels in loader:
                    features = features.to(device)
                    labels = labels.to(device)
                    optimizer.zero_grad(set_to_none=True)
                    with torch.cuda.amp.autocast(enabled=device.type == "cuda"):
                        logits = model(features)
                        loss = criterion(logits, labels)
                    scaler.scale(loss).backward()
                    scaler.step(optimizer)
                    scaler.update()


            @torch.no_grad()
            def run_validation(model, loader, criterion, device):
                model.eval()
                model.to(device)
                total_loss = 0.0
                for features, labels in loader:
                    features = features.to(device)
                    labels = labels.to(device)
                    logits = model(features)
                    total_loss += float(criterion(logits, labels).item())
                return total_loss / max(len(loader), 1)
            """
        ).strip()
        if variant == "amp"
        else dedent(
            """
            import torch


            def run_epoch(model, loader, optimizer, criterion, device):
                model.train()
                model.to(device)
                for features, labels in loader:
                    features = features.to(device)
                    labels = labels.to(device)
                    optimizer.zero_grad(set_to_none=True)
                    logits = model(features)
                    loss = criterion(logits, labels)
                    loss.backward()
                    optimizer.step()


            @torch.no_grad()
            def run_validation(model, loader, criterion, device):
                model.eval()
                model.to(device)
                total_loss = 0.0
                for features, labels in loader:
                    features = features.to(device)
                    labels = labels.to(device)
                    logits = model(features)
                    total_loss += float(criterion(logits, labels).item())
                return total_loss / max(len(loader), 1)
            """
        ).strip()
    )
    return _bundle(
        "training_loop",
        variant,
        f"PyTorch training loop ({variant})",
        "Generate a PyTorch loop with explicit train/eval phases and less magical state leakage.",
        ["torch"],
        {
            "pytorch_starters/training_loop.py": training_loop_content,
        },
        [
            "Run one train epoch and one validation epoch on a toy batch.",
            "Verify loss is finite and gradients are not silently skipped.",
        ],
        [
            "Capture device, amp state, and whether validation ran separately from training.",
        ],
    )


def _distributed_training_bundle(variant: str) -> PyTorchFeatureBundle:
    if variant not in {"ddp", "accelerate", "deepspeed"}:
        raise ValueError(f"Unsupported distributed training variant `{variant}`.")
    body = {
        "ddp": """
            import os
            import torch
            import torch.distributed as dist
            from torch.nn.parallel import DistributedDataParallel as DDP


            def setup() -> tuple[int, int]:
                backend = "nccl" if torch.cuda.is_available() else "gloo"
                dist.init_process_group(backend)
                rank = int(os.environ["RANK"])
                local_rank = int(os.environ.get("LOCAL_RANK", "0"))
                if torch.cuda.is_available():
                    torch.cuda.set_device(local_rank)
                return rank, local_rank


            def wrap(model: torch.nn.Module) -> torch.nn.Module:
                _, local_rank = setup()
                if torch.cuda.is_available():
                    return DDP(model.to(local_rank), device_ids=[local_rank])
                return DDP(model)
        """,
        "accelerate": """
            from accelerate import Accelerator


            accelerator = Accelerator(mixed_precision="bf16")


            def prepare(model, optimizer, loader):
                return accelerator.prepare(model, optimizer, loader)
        """,
        "deepspeed": """
            import deepspeed


            def initialize(model, optimizer, loader):
                model_engine, optimizer, _, loader = deepspeed.initialize(
                    model=model,
                    optimizer=optimizer,
                    training_data=loader.dataset,
                    config="ds_config.json",
                )
                return model_engine, optimizer, loader
        """,
    }[variant]
    return _bundle(
        "distributed_training",
        variant,
        f"PyTorch distributed training ({variant})",
        "Generate launcher-aware distributed scaffolding with fewer rank and device-placement own goals.",
        ["torch", "accelerate" if variant == "accelerate" else "deepspeed" if variant == "deepspeed" else "torch"],
        {"pytorch_starters/distributed.py": body},
        [
            "Run the distributed launcher on a toy workload before trusting the configuration.",
            "Verify rank/world-size environment handling and checkpoint ownership rules.",
        ],
        [
            "Capture launcher command, world size, rank mapping, and device placement evidence.",
        ],
    )


def _checkpoint_resume_bundle(variant: str) -> PyTorchFeatureBundle:
    if variant not in {"single_gpu", "distributed"}:
        raise ValueError(f"Unsupported checkpoint variant `{variant}`.")
    return _bundle(
        "checkpoint_resume",
        variant,
        f"PyTorch checkpoint guardrails ({variant})",
        "Save and restore model, optimizer, and scaler state without pretending weights alone are a resume story.",
        ["torch"],
        {
            "pytorch_starters/checkpoints.py": """
                from pathlib import Path

                import torch


                def save_checkpoint(path, model, optimizer, epoch, scaler=None):
                    Path(path).parent.mkdir(parents=True, exist_ok=True)
                    payload = {
                        "model": model.state_dict(),
                        "optimizer": optimizer.state_dict(),
                        "epoch": epoch,
                    }
                    if scaler is not None:
                        payload["scaler"] = scaler.state_dict()
                    torch.save(payload, path)


                def load_checkpoint(path, model, optimizer, scaler=None, map_location="cpu"):
                    payload = torch.load(path, map_location=map_location, weights_only=False)
                    model.load_state_dict(payload["model"])
                    optimizer.load_state_dict(payload["optimizer"])
                    if scaler is not None and "scaler" in payload:
                        scaler.load_state_dict(payload["scaler"])
                    return int(payload.get("epoch", 0))
            """,
        },
        [
            "Write a checkpoint, reload it, and prove optimizer state survives the round trip.",
            "Verify resume epoch and any scaler state before calling the run reproducible.",
        ],
        [
            "Record checkpoint path, load status, and whether optimizer/scaler state restored cleanly.",
        ],
    )


def _profiler_observability_bundle(variant: str) -> PyTorchFeatureBundle:
    if variant != "default":
        raise ValueError(f"Unsupported profiler variant `{variant}`.")
    return _bundle(
        "profiler_observability",
        variant,
        "PyTorch profiler observability",
        "Collect torch.profiler traces and TensorBoard logs before claiming you optimized anything.",
        ["torch", "tensorboard"],
        {
            "pytorch_starters/profiler.py": """
                from pathlib import Path

                import torch


                def profile_step(model, batch, logdir="artifacts/tensorboard"):
                    Path(logdir).mkdir(parents=True, exist_ok=True)
                    activities = [torch.profiler.ProfilerActivity.CPU]
                    if torch.cuda.is_available():
                        activities.append(torch.profiler.ProfilerActivity.CUDA)
                    with torch.profiler.profile(
                        activities=activities,
                        schedule=torch.profiler.schedule(wait=1, warmup=1, active=2),
                        on_trace_ready=torch.profiler.tensorboard_trace_handler(logdir),
                        record_shapes=True,
                        profile_memory=True,
                    ) as prof:
                        for _ in range(4):
                            outputs = model(batch)
                            if isinstance(outputs, torch.Tensor):
                                outputs.sum().backward()
                            prof.step()
            """,
        },
        [
            "Run a short profiler capture and open the TensorBoard trace output.",
            "Compare dataloader wait time and kernel time before pretending throughput is solved.",
        ],
        [
            "Capture profiler logdir, dominant kernels, and dataloader wait evidence.",
        ],
    )


def _export_inference_bundle(variant: str) -> PyTorchFeatureBundle:
    if variant != "torchscript_onnx":
        raise ValueError(f"Unsupported export variant `{variant}`.")
    return _bundle(
        "export_inference",
        variant,
        "PyTorch export and inference guardrails",
        "Export TorchScript and ONNX artifacts and prove they can load again before shipping fiction.",
        ["torch", "onnx"],
        {
            "pytorch_starters/export.py": """
                from pathlib import Path

                import torch


                def export_artifacts(model: torch.nn.Module, sample: torch.Tensor) -> None:
                    Path("artifacts").mkdir(parents=True, exist_ok=True)
                    model.eval()
                    scripted = torch.jit.trace(model, sample)
                    scripted.save("artifacts/model.ts")
                    torch.onnx.export(
                        model,
                        sample,
                        "artifacts/model.onnx",
                        input_names=["inputs"],
                        output_names=["logits"],
                        dynamic_axes={"inputs": {0: "batch"}, "logits": {0: "batch"}},
                    )
            """,
            "pytorch_starters/infer.py": """
                import torch


                def load_torchscript(path="artifacts/model.ts"):
                    model = torch.jit.load(path, map_location="cpu")
                    model.eval()
                    return model
            """,
        },
        [
            "Export TorchScript and ONNX artifacts from a representative sample input.",
            "Reload the TorchScript artifact and run one inference pass.",
        ],
        [
            "Show export artifact paths and a successful reload/inference result.",
        ],
    )


def _peft_finetuning_bundle(variant: str) -> PyTorchFeatureBundle:
    if variant != "lora_transformer":
        raise ValueError(f"Unsupported PEFT variant `{variant}`.")
    return _bundle(
        "peft_finetuning",
        variant,
        "PyTorch LoRA fine-tuning starter",
        "Generate a LoRA/PEFT setup with explicit adapter scope and trainable-parameter accounting.",
        ["torch", "transformers", "peft"],
        {
            "pytorch_starters/peft_finetune.py": """
                from peft import LoraConfig, get_peft_model
                from transformers import AutoModelForCausalLM


                def build_model(model_name: str = "distilbert/distilgpt2"):
                    model = AutoModelForCausalLM.from_pretrained(model_name)
                    config = LoraConfig(
                        r=16,
                        lora_alpha=32,
                        lora_dropout=0.05,
                        target_modules=["c_attn"],
                        bias="none",
                        task_type="CAUSAL_LM",
                    )
                    model = get_peft_model(model, config)
                    model.print_trainable_parameters()
                    return model
            """,
        },
        [
            "Print trainable-parameter counts before training.",
            "Verify adapter merge or save behavior before calling the fine-tune path complete.",
        ],
        [
            "Capture trainable-parameter counts, adapter artifact paths, and merge behavior.",
        ],
    )
