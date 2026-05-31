from __future__ import annotations

from tensorflow_starters import generate_tensorflow_feature_bundle, tensorflow_feature_catalog


def test_tensorflow_feature_catalog_covers_the_full_product_list() -> None:
    catalog = tensorflow_feature_catalog()

    assert len(catalog) == 15
    feature_ids = {item["feature_id"] for item in catalog}
    assert feature_ids == {
        "keras_scaffold",
        "tf_data_pipeline",
        "pretrained_finetuning",
        "training_loop",
        "distributed_training",
        "tensorboard_observability",
        "hyperparameter_tuning",
        "model_export_guardrails",
        "serving_api",
        "tfx_pipeline",
        "data_validation",
        "skew_prevention",
        "evaluation_by_slice",
        "on_device_deployment",
        "optimization_advisor",
    }


def test_generate_keras_classification_starter_contains_modern_keras_shape() -> None:
    bundle = generate_tensorflow_feature_bundle("keras_scaffold", variant="classification")

    assert bundle["title"].lower().startswith("keras classification")
    assert "tensorflow_starters/model.py" in bundle["files"]
    assert "import keras" in bundle["files"]["tensorflow_starters/model.py"]
    assert "keras.Input" in bundle["files"]["tensorflow_starters/model.py"]
    assert "SparseCategoricalCrossentropy" in bundle["files"]["tensorflow_starters/model.py"]
    assert "artifacts/final.keras" in bundle["files"]["tensorflow_starters/train.py"]


def test_generate_tf_data_csv_pipeline_contains_cache_and_prefetch() -> None:
    bundle = generate_tensorflow_feature_bundle("tf_data_pipeline", variant="csv")
    content = bundle["files"]["tensorflow_starters/data_pipeline.py"]

    assert "make_csv_dataset" in content
    assert ".shuffle(" in content
    assert ".cache()" in content
    assert "prefetch(tf.data.AUTOTUNE)" in content


def test_generate_finetuning_and_custom_loop_bundles_cover_transfer_learning_and_escape_hatch() -> None:
    finetune = generate_tensorflow_feature_bundle("pretrained_finetuning", variant="image_classifier")
    custom_loop = generate_tensorflow_feature_bundle("training_loop", variant="custom_gradient_tape")

    assert "hub.KerasLayer" in finetune["files"]["tensorflow_starters/finetune.py"]
    assert "trainable = False" in finetune["files"]["tensorflow_starters/finetune.py"]
    assert "tf.GradientTape()" in custom_loop["files"]["tensorflow_starters/custom_loop.py"]


def test_generate_distribution_observability_tuning_and_export_bundles_cover_key_runtime_features() -> None:
    distributed = generate_tensorflow_feature_bundle("distributed_training", variant="multi_worker")
    observability = generate_tensorflow_feature_bundle("tensorboard_observability")
    tuning = generate_tensorflow_feature_bundle("hyperparameter_tuning", variant="hyperband")
    export = generate_tensorflow_feature_bundle("model_export_guardrails")

    assert "TF_CONFIG" in distributed["files"]["tensorflow_starters/distribute.py"]
    assert "MultiWorkerMirroredStrategy" in distributed["files"]["tensorflow_starters/distribute.py"]
    assert "keras.callbacks.TensorBoard" in observability["files"]["tensorflow_starters/observability.py"]
    assert "keras_tuner.Hyperband" in tuning["files"]["tensorflow_starters/tune.py"]
    assert "model.save(\"artifacts/model.keras\")" in export["files"]["tensorflow_starters/export.py"]
    assert "model.export(\"artifacts/exported_model\")" in export["files"]["tensorflow_starters/export.py"]


def test_generate_serving_tfx_validation_skew_slice_lite_and_optimization_bundles_cover_product_systems() -> None:
    serving = generate_tensorflow_feature_bundle("serving_api")
    tfx = generate_tensorflow_feature_bundle("tfx_pipeline")
    validation = generate_tensorflow_feature_bundle("data_validation")
    skew = generate_tensorflow_feature_bundle("skew_prevention")
    slices = generate_tensorflow_feature_bundle("evaluation_by_slice")
    lite = generate_tensorflow_feature_bundle("on_device_deployment")
    optimize = generate_tensorflow_feature_bundle("optimization_advisor")

    assert "base_path" in serving["files"]["tensorflow_starters/serving/models.config"]
    assert "FastAPI" in serving["files"]["tensorflow_starters/serving/api.py"]
    assert "ExampleValidator" in tfx["files"]["tensorflow_starters/tfx_pipeline.py"]
    assert "InfraValidator" in tfx["files"]["tensorflow_starters/tfx_pipeline.py"]
    assert "tfdv.infer_schema" in validation["files"]["tensorflow_starters/data_validation.py"]
    assert "tft.compute_and_apply_vocabulary" in skew["files"]["tensorflow_starters/preprocessing.py"]
    assert "tfma.SlicingSpec" in slices["files"]["tensorflow_starters/eval_config.py"]
    assert "tf.lite.TFLiteConverter" in lite["files"]["tensorflow_starters/tflite_export.py"]
    assert "quantization" in optimize["files"]["tensorflow_starters/optimization_advisor.md"].lower()
