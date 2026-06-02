from __future__ import annotations

import pytest

from pytorch_starters import generate_pytorch_feature_bundle, pytorch_feature_catalog


pytestmark = pytest.mark.no_db_reset


def test_pytorch_feature_catalog_covers_the_core_product_list() -> None:
    catalog = pytorch_feature_catalog()

    assert len(catalog) == 8
    feature_ids = {item["feature_id"] for item in catalog}
    assert feature_ids == {
        "project_scaffold",
        "dataset_dataloader",
        "training_loop",
        "distributed_training",
        "checkpoint_resume",
        "profiler_observability",
        "export_inference",
        "peft_finetuning",
    }


def test_generate_project_scaffold_bundle_contains_model_data_and_training_files() -> None:
    bundle = generate_pytorch_feature_bundle("project_scaffold", variant="classification")

    assert bundle["title"].lower().startswith("pytorch classification")
    assert "pytorch_starters/model.py" in bundle["files"]
    assert "class DemoModel" in bundle["files"]["pytorch_starters/model.py"]
    assert 'Path("artifacts").mkdir(parents=True, exist_ok=True)' in bundle["files"]["pytorch_starters/train.py"]
    assert "loss.backward()" in bundle["files"]["pytorch_starters/train.py"]
    assert "DataLoader" in bundle["files"]["pytorch_starters/data.py"]


def test_generate_project_scaffold_variants_emit_real_vision_and_nlp_shapes() -> None:
    vision = generate_pytorch_feature_bundle("project_scaffold", variant="vision")
    nlp = generate_pytorch_feature_bundle("project_scaffold", variant="nlp")

    assert "torch.nn.Conv2d(3, 16" in vision["files"]["pytorch_starters/model.py"]
    assert "images = torch.zeros((128, 3, 64, 64)" in vision["files"]["pytorch_starters/data.py"]
    assert "torch.nn.Embedding(vocab_size, hidden_dim)" in nlp["files"]["pytorch_starters/model.py"]
    assert "tokens = torch.zeros((128, 32), dtype=torch.long)" in nlp["files"]["pytorch_starters/data.py"]
    assert "torch.nn.Linear(hidden_dim, num_classes)" in nlp["files"]["pytorch_starters/model.py"]
    assert "model.eval()" in vision["files"]["pytorch_starters/train.py"]


def test_generate_dataset_dataloader_bundle_aligns_tabular_shape_and_text_batch_contract() -> None:
    tabular = generate_pytorch_feature_bundle("dataset_dataloader", variant="tabular")
    text = generate_pytorch_feature_bundle("dataset_dataloader", variant="text")

    assert "features = torch.zeros(128, dtype=torch.float32)" in tabular["files"]["pytorch_starters/dataloader.py"]
    assert '"input_ids": tokens["input_ids"].squeeze(0)' in text["files"]["pytorch_starters/dataloader.py"]
    assert '"attention_mask": tokens["attention_mask"].squeeze(0)' in text["files"]["pytorch_starters/dataloader.py"]
    assert '"labels": torch.tensor(index % 2, dtype=torch.long)' in text["files"]["pytorch_starters/dataloader.py"]


def test_generate_training_loop_bundle_handles_dict_and_multi_input_batches() -> None:
    basic = generate_pytorch_feature_bundle("training_loop", variant="basic")
    amp = generate_pytorch_feature_bundle("training_loop", variant="amp")

    for bundle in (basic, amp):
        content = bundle["files"]["pytorch_starters/training_loop.py"]
        assert "def _move_to_device(value, device):" in content
        assert "def _split_supervised_batch(batch):" in content
        assert 'labels = batch.get("labels", batch.get("label"))' in content
        assert 'if not features:' in content
        assert "Expected at least one model input alongside labels in the dict batch." in content
        assert 'features = batch[0] if len(batch) == 2 else batch[:-1]' in content
        assert "def _run_model(model, features):" in content
        assert "def _extract_logits(outputs):" in content
        assert 'logits = getattr(outputs, "logits", None)' in content
        assert "return model(**features)" in content
        assert "return model(*features)" in content
        assert "for batch in loader:" in content


def test_generate_distributed_profiler_export_and_peft_bundles_cover_runtime_features() -> None:
    distributed = generate_pytorch_feature_bundle("distributed_training", variant="ddp")
    accelerate = generate_pytorch_feature_bundle("distributed_training", variant="accelerate")
    profiler = generate_pytorch_feature_bundle("profiler_observability")
    export = generate_pytorch_feature_bundle("export_inference")
    peft = generate_pytorch_feature_bundle("peft_finetuning")

    assert "DistributedDataParallel" in distributed["files"]["pytorch_starters/distributed.py"]
    assert 'backend = "nccl" if torch.cuda.is_available() else "gloo"' in distributed["files"]["pytorch_starters/distributed.py"]
    assert 'if not dist.is_initialized()' in distributed["files"]["pytorch_starters/distributed.py"]
    assert 'os.environ.get("RANK", "0")' in distributed["files"]["pytorch_starters/distributed.py"]
    assert 'if world_size <= 1:' in distributed["files"]["pytorch_starters/distributed.py"]
    assert 'Set MASTER_ADDR and MASTER_PORT before starting DDP with more than one process.' in distributed["files"]["pytorch_starters/distributed.py"]
    assert 'if not dist.is_initialized():' in distributed["files"]["pytorch_starters/distributed.py"]
    assert 'return model.to(local_rank) if torch.cuda.is_available() else model' in distributed["files"]["pytorch_starters/distributed.py"]
    assert 'Accelerator(' in accelerate["files"]["pytorch_starters/distributed.py"]
    assert 'torch.cuda.is_bf16_supported()' in accelerate["files"]["pytorch_starters/distributed.py"]
    assert "torch.profiler.profile" in profiler["files"]["pytorch_starters/profiler.py"]
    assert "def _model_inputs_from_batch(batch):" in profiler["files"]["pytorch_starters/profiler.py"]
    assert 'features = {key: value for key, value in batch.items() if key not in {"labels", "label"}}' in profiler["files"]["pytorch_starters/profiler.py"]
    assert "return batch[0] if len(batch) == 2 else batch[:-1]" in profiler["files"]["pytorch_starters/profiler.py"]
    assert "def _forward_model(model, batch, device):" in profiler["files"]["pytorch_starters/profiler.py"]
    assert "def _extract_tensor_output(outputs):" in profiler["files"]["pytorch_starters/profiler.py"]
    assert 'loss = getattr(outputs, "loss", None)' in profiler["files"]["pytorch_starters/profiler.py"]
    assert 'logits = getattr(outputs, "logits", None)' in profiler["files"]["pytorch_starters/profiler.py"]
    assert "model.zero_grad(set_to_none=True)" in profiler["files"]["pytorch_starters/profiler.py"]
    assert 'device = first_parameter.device if first_parameter is not None else torch.device("cpu")' in profiler["files"]["pytorch_starters/profiler.py"]
    assert "activities = [torch.profiler.ProfilerActivity.CPU]" in profiler["files"]["pytorch_starters/profiler.py"]
    assert "torch.onnx.export" in export["files"]["pytorch_starters/export.py"]
    assert "def _normalize_sample(sample, device):" in export["files"]["pytorch_starters/export.py"]
    assert "Dict-style export samples need a repo-specific wrapper" in export["files"]["pytorch_starters/export.py"]
    assert "Provide at least one sample tensor before tracing or ONNX export." in export["files"]["pytorch_starters/export.py"]
    assert 'model = model.to(device)' in export["files"]["pytorch_starters/export.py"]
    assert 'sample.device if isinstance(sample, torch.Tensor) else sample[0].device' in export["files"]["pytorch_starters/export.py"]
    assert "def _input_names(sample):" in export["files"]["pytorch_starters/export.py"]
    assert 'return [f"inputs_{index}" for index, _value in enumerate(sample)]' in export["files"]["pytorch_starters/export.py"]
    assert "def _dynamic_axes(sample, output_name=\"logits\"):" in export["files"]["pytorch_starters/export.py"]
    assert "dynamic_axes=_dynamic_axes(sample)" in export["files"]["pytorch_starters/export.py"]
    assert "model.eval()" in export["files"]["pytorch_starters/export.py"]
    assert 'Path("artifacts").mkdir(parents=True, exist_ok=True)' in export["files"]["pytorch_starters/export.py"]
    assert "get_peft_model" in peft["files"]["pytorch_starters/peft_finetune.py"]
    assert 'target_modules=["c_attn"]' in peft["files"]["pytorch_starters/peft_finetune.py"]
    assert 'def build_model(model_name: str = "distilgpt2")' in peft["files"]["pytorch_starters/peft_finetune.py"]


def test_generate_checkpoint_bundle_creates_parent_directory_before_save() -> None:
    bundle = generate_pytorch_feature_bundle("checkpoint_resume")

    assert "Path(path).parent.mkdir(parents=True, exist_ok=True)" in bundle["files"]["pytorch_starters/checkpoints.py"]


def test_generated_pytorch_python_snippets_compile_for_core_variants() -> None:
    for entry in pytorch_feature_catalog():
        for variant in entry["variants"]:
            bundle = generate_pytorch_feature_bundle(entry["feature_id"], variant=variant)
            for path, content in bundle["files"].items():
                if path.endswith(".py"):
                    compile(content, path, "exec")
