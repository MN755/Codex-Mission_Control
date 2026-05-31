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
    assert "loss.backward()" in bundle["files"]["pytorch_starters/train.py"]
    assert "DataLoader" in bundle["files"]["pytorch_starters/data.py"]


def test_generate_distributed_profiler_export_and_peft_bundles_cover_runtime_features() -> None:
    distributed = generate_pytorch_feature_bundle("distributed_training", variant="ddp")
    profiler = generate_pytorch_feature_bundle("profiler_observability")
    export = generate_pytorch_feature_bundle("export_inference")
    peft = generate_pytorch_feature_bundle("peft_finetuning")

    assert "DistributedDataParallel" in distributed["files"]["pytorch_starters/distributed.py"]
    assert "torch.profiler.profile" in profiler["files"]["pytorch_starters/profiler.py"]
    assert "torch.onnx.export" in export["files"]["pytorch_starters/export.py"]
    assert "get_peft_model" in peft["files"]["pytorch_starters/peft_finetune.py"]
