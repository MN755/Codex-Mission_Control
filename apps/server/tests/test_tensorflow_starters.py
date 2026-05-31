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
    assert 'Path("artifacts").mkdir(parents=True, exist_ok=True)' in bundle["files"]["tensorflow_starters/train.py"]
    assert "artifacts/final.keras" in bundle["files"]["tensorflow_starters/train.py"]


def test_generate_keras_scaffold_variants_emit_variant_specific_models_and_data() -> None:
    regression = generate_tensorflow_feature_bundle("keras_scaffold", variant="regression")
    nlp = generate_tensorflow_feature_bundle("keras_scaffold", variant="nlp")
    vision = generate_tensorflow_feature_bundle("keras_scaffold", variant="vision")
    time_series = generate_tensorflow_feature_bundle("keras_scaffold", variant="time_series")

    assert "keras.losses.MeanSquaredError()" in regression["files"]["tensorflow_starters/model.py"]
    assert "tf.zeros((256, FEATURE_DIM), dtype=tf.float32), tf.zeros((256, 1), dtype=tf.float32)" in regression["files"]["tensorflow_starters/data.py"]
    assert "keras.layers.Embedding(VOCAB_SIZE, 128)" in nlp["files"]["tensorflow_starters/model.py"]
    assert "tf.zeros((256, SEQUENCE_LENGTH), dtype=tf.int32)" in nlp["files"]["tensorflow_starters/data.py"]
    assert "keras.layers.Conv2D(32, 3, activation='relu')" in vision["files"]["tensorflow_starters/model.py"]
    assert "tf.zeros((256, IMAGE_HEIGHT, IMAGE_WIDTH, 3), dtype=tf.float32)" in vision["files"]["tensorflow_starters/data.py"]
    assert "keras.layers.LayerNormalization()" in time_series["files"]["tensorflow_starters/model.py"]
    assert "tf.zeros((256, WINDOW_SIZE), dtype=tf.float32), tf.zeros((256, 1), dtype=tf.float32)" in time_series["files"]["tensorflow_starters/data.py"]


def test_generate_tf_data_csv_pipeline_contains_cache_and_prefetch() -> None:
    bundle = generate_tensorflow_feature_bundle("tf_data_pipeline", variant="csv")
    content = bundle["files"]["tensorflow_starters/data_pipeline.py"]

    assert "make_csv_dataset" in content
    assert ".shuffle(" in content
    assert ".cache()" in content
    assert "prefetch(tf.data.AUTOTUNE)" in content


def test_generate_tf_data_generator_pipeline_batches_generated_records() -> None:
    bundle = generate_tensorflow_feature_bundle("tf_data_pipeline", variant="generator")
    content = bundle["files"]["tensorflow_starters/data_pipeline.py"]

    assert "def generator_fn()" in content
    assert "output_signature" in content
    assert "dataset = dataset if False else dataset.batch(64)" in content


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
    assert 'Path("artifacts/metrics").mkdir(parents=True, exist_ok=True)' in observability["files"]["tensorflow_starters/observability.py"]
    assert "keras_tuner.Hyperband" in tuning["files"]["tensorflow_starters/tune.py"]
    assert "max_epochs=12" in tuning["files"]["tensorflow_starters/tune.py"]
    assert "factor=3" in tuning["files"]["tensorflow_starters/tune.py"]
    assert "max_trials=12" not in tuning["files"]["tensorflow_starters/tune.py"]
    assert "model.save(\"artifacts/model.keras\")" in export["files"]["tensorflow_starters/export.py"]
    assert "def build_serving_signature(model: keras.Model):" in export["files"]["tensorflow_starters/export.py"]
    assert "tf.saved_model.save(model, \"artifacts/exported_model\"" in export["files"]["tensorflow_starters/export.py"]


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
    assert "model.export(fn_args.serving_model_dir)" in tfx["files"]["tensorflow_starters/trainer.py"]
    assert "tfdv.infer_schema" in validation["files"]["tensorflow_starters/data_validation.py"]
    assert "tft.compute_and_apply_vocabulary" in skew["files"]["tensorflow_starters/preprocessing.py"]
    assert "tfma.SlicingSpec" in slices["files"]["tensorflow_starters/eval_config.py"]
    assert "tf.lite.TFLiteConverter" in lite["files"]["tensorflow_starters/tflite_export.py"]
    assert "Path(output_path).parent.mkdir(parents=True, exist_ok=True)" in lite["files"]["tensorflow_starters/tflite_export.py"]
    assert "MappedByteBuffer" in lite["files"]["tensorflow_starters/mobile_integration.kt"]
    assert "Interpreter" in lite["files"]["tensorflow_starters/mobile_integration.kt"]
    assert "Path(output_path).parent.mkdir(parents=True, exist_ok=True)" in optimize["files"]["tensorflow_starters/quantize.py"]
    assert "quantization" in optimize["files"]["tensorflow_starters/optimization_advisor.md"].lower()


def test_generated_tensorflow_python_snippets_compile_for_core_variants() -> None:
    for entry in tensorflow_feature_catalog():
        for variant in entry["variants"]:
            bundle = generate_tensorflow_feature_bundle(entry["feature_id"], variant=variant)
            for path, content in bundle["files"].items():
                if path.endswith(".py"):
                    compile(content, path, "exec")
