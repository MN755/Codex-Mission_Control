from __future__ import annotations

from pytorch_starters import generate_pytorch_feature_bundle, pytorch_feature_catalog


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


def test_generate_distributed_profiler_export_and_peft_bundles_cover_runtime_features() -> None:
    distributed = generate_pytorch_feature_bundle("distributed_training", variant="ddp")
    profiler = generate_pytorch_feature_bundle("profiler_observability")
    export = generate_pytorch_feature_bundle("export_inference")
    peft = generate_pytorch_feature_bundle("peft_finetuning")

    assert "DistributedDataParallel" in distributed["files"]["pytorch_starters/distributed.py"]
    assert 'backend = "nccl" if torch.cuda.is_available() else "gloo"' in distributed["files"]["pytorch_starters/distributed.py"]
    assert "torch.profiler.profile" in profiler["files"]["pytorch_starters/profiler.py"]
    assert "activities = [torch.profiler.ProfilerActivity.CPU]" in profiler["files"]["pytorch_starters/profiler.py"]
    assert "torch.onnx.export" in export["files"]["pytorch_starters/export.py"]
    assert "model.eval()" in export["files"]["pytorch_starters/export.py"]
    assert 'Path("artifacts").mkdir(parents=True, exist_ok=True)' in export["files"]["pytorch_starters/export.py"]
    assert "get_peft_model" in peft["files"]["pytorch_starters/peft_finetune.py"]
    assert 'target_modules=["c_attn"]' in peft["files"]["pytorch_starters/peft_finetune.py"]


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
