from __future__ import annotations

from dataclasses import asdict, dataclass
from textwrap import dedent, indent
from typing import Any


@dataclass(frozen=True)
class TensorFlowFeatureBundle:
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


def tensorflow_feature_catalog() -> list[dict[str, Any]]:
    return [
        {
            "feature_id": "keras_scaffold",
            "title": "Keras-first project scaffolding",
            "variants": ["classification", "regression", "nlp", "vision", "time_series"],
            "summary": "Generate product-shaped Keras starters instead of disposable notebook soup.",
        },
        {
            "feature_id": "tf_data_pipeline",
            "title": "tf.data pipeline builder",
            "variants": ["csv", "tfrecord", "images", "text", "generator"],
            "summary": "Build TensorFlow input pipelines with batching, caching, and prefetching already wired.",
        },
        {
            "feature_id": "pretrained_finetuning",
            "title": "Pretrained model and fine-tuning assistant",
            "variants": ["image_classifier", "text_encoder"],
            "summary": "Start transfer-learning work from TensorFlow Hub templates instead of raw guesswork.",
        },
        {
            "feature_id": "training_loop",
            "title": "Training-loop generator",
            "variants": ["model_fit", "custom_gradient_tape"],
            "summary": "Support both Keras fit loops and custom lower-level loops.",
        },
        {
            "feature_id": "distributed_training",
            "title": "Distributed training setup",
            "variants": ["mirrored", "multi_worker"],
            "summary": "Wire single-node multi-GPU and multi-worker TensorFlow distribution templates.",
        },
        {
            "feature_id": "tensorboard_observability",
            "title": "TensorBoard-integrated observability",
            "variants": ["default"],
            "summary": "Auto-wire logs, graphs, profiling, and run-comparison guidance.",
        },
        {
            "feature_id": "hyperparameter_tuning",
            "title": "Hyperparameter tuning workflows",
            "variants": ["random_search", "bayesian_optimization", "hyperband"],
            "summary": "Create bounded KerasTuner recipes with baseline-aware validation.",
        },
        {
            "feature_id": "model_export_guardrails",
            "title": "Model saving and export guardrails",
            "variants": ["savedmodel_and_keras"],
            "summary": "Keep training artifacts and serving artifacts separate and explicit.",
        },
        {
            "feature_id": "serving_api",
            "title": "Serving/API deployment scaffolding",
            "variants": ["tensorflow_serving_fastapi"],
            "summary": "Generate TensorFlow Serving config plus a minimal inference API wrapper.",
        },
        {
            "feature_id": "tfx_pipeline",
            "title": "Production pipeline generator with TFX",
            "variants": ["end_to_end"],
            "summary": "Generate an end-to-end TFX-style product pipeline skeleton.",
        },
        {
            "feature_id": "data_validation",
            "title": "Data validation and schema enforcement",
            "variants": ["tfdv_schema"],
            "summary": "Surface dataset stats, schema drift, missing features, and anomalies early.",
        },
        {
            "feature_id": "skew_prevention",
            "title": "Training/serving skew prevention",
            "variants": ["tensorflow_transform"],
            "summary": "Reuse preprocessing logic across training and serving using TFT-style flows.",
        },
        {
            "feature_id": "evaluation_by_slice",
            "title": "Model evaluation by slice",
            "variants": ["tfma_slices"],
            "summary": "Generate slice-aware evaluation configs instead of relying on one aggregate metric.",
        },
        {
            "feature_id": "on_device_deployment",
            "title": "On-device deployment workflows",
            "variants": ["tflite_mobile"],
            "summary": "Export TensorFlow Lite artifacts and mobile integration scaffolding.",
        },
        {
            "feature_id": "optimization_advisor",
            "title": "Optimization advisor for edge deployment",
            "variants": ["mobile_edge"],
            "summary": "Recommend quantization, pruning, and deployment-aware tradeoffs before shipping.",
        },
    ]


def get_tensorflow_feature_catalog_entry(feature_id: str) -> dict[str, Any]:
    normalized_feature = str(feature_id or "").strip().lower()
    for entry in tensorflow_feature_catalog():
        if entry["feature_id"] == normalized_feature:
            return dict(entry)
    raise ValueError(f"Unknown TensorFlow feature bundle `{feature_id}`.")


def generate_tensorflow_feature_bundle(feature_id: str, *, variant: str | None = None) -> dict[str, Any]:
    normalized_feature = str(feature_id or "").strip().lower()
    normalized_variant = str(variant or "").strip().lower() or _default_variant(normalized_feature)
    bundle = _bundle_dispatch(normalized_feature, normalized_variant)
    return bundle.to_dict()


def _default_variant(feature_id: str) -> str:
    defaults = {
        "keras_scaffold": "classification",
        "tf_data_pipeline": "csv",
        "pretrained_finetuning": "image_classifier",
        "training_loop": "model_fit",
        "distributed_training": "mirrored",
        "tensorboard_observability": "default",
        "hyperparameter_tuning": "random_search",
        "model_export_guardrails": "savedmodel_and_keras",
        "serving_api": "tensorflow_serving_fastapi",
        "tfx_pipeline": "end_to_end",
        "data_validation": "tfdv_schema",
        "skew_prevention": "tensorflow_transform",
        "evaluation_by_slice": "tfma_slices",
        "on_device_deployment": "tflite_mobile",
        "optimization_advisor": "mobile_edge",
    }
    return defaults[feature_id]


def _bundle_dispatch(feature_id: str, variant: str) -> TensorFlowFeatureBundle:
    builders = {
        "keras_scaffold": _keras_scaffold_bundle,
        "tf_data_pipeline": _tf_data_bundle,
        "pretrained_finetuning": _finetuning_bundle,
        "training_loop": _training_loop_bundle,
        "distributed_training": _distributed_bundle,
        "tensorboard_observability": _tensorboard_bundle,
        "hyperparameter_tuning": _tuning_bundle,
        "model_export_guardrails": _export_bundle,
        "serving_api": _serving_bundle,
        "tfx_pipeline": _tfx_bundle,
        "data_validation": _data_validation_bundle,
        "skew_prevention": _skew_prevention_bundle,
        "evaluation_by_slice": _slice_eval_bundle,
        "on_device_deployment": _tflite_bundle,
        "optimization_advisor": _optimization_bundle,
    }
    if feature_id not in builders:
        raise ValueError(f"Unknown TensorFlow feature bundle `{feature_id}`.")
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
) -> TensorFlowFeatureBundle:
    return TensorFlowFeatureBundle(
        feature_id=feature_id,
        variant=variant,
        title=title,
        summary=summary,
        dependencies=dependencies,
        files={path: dedent(content).strip() + "\n" for path, content in files.items()},
        validation_steps=validation_steps,
        evidence_targets=evidence_targets,
    )


def _keras_scaffold_bundle(variant: str) -> TensorFlowFeatureBundle:
    model_heads = {
        "classification": (
            "keras.layers.Dense(NUM_CLASSES, activation='softmax')",
            "keras.losses.SparseCategoricalCrossentropy()",
            "['accuracy']",
        ),
        "regression": (
            "keras.layers.Dense(1)",
            "keras.losses.MeanSquaredError()",
            "['mae']",
        ),
        "nlp": (
            "keras.layers.Dense(NUM_CLASSES, activation='softmax')",
            "keras.losses.SparseCategoricalCrossentropy()",
            "['accuracy']",
        ),
        "vision": (
            "keras.layers.Dense(NUM_CLASSES, activation='softmax')",
            "keras.losses.SparseCategoricalCrossentropy()",
            "['accuracy']",
        ),
        "time_series": (
            "keras.layers.Dense(1)",
            "keras.losses.MeanSquaredError()",
            "['mae']",
        ),
    }
    if variant not in model_heads:
        raise ValueError(f"Unsupported Keras scaffold variant `{variant}`.")
    head, loss, metrics = model_heads[variant]
    encoder = {
        "classification": dedent(
            """
            features = keras.layers.Dense(128, activation='relu')(inputs)
            """
        ).strip(),
        "regression": dedent(
            """
            features = keras.layers.Dense(128, activation='relu')(inputs)
            """
        ).strip(),
        "nlp": dedent(
            """
            features = keras.layers.Embedding(VOCAB_SIZE, 128)(inputs)
            features = keras.layers.GlobalAveragePooling1D()(features)
            """
        ).strip(),
        "vision": dedent(
            """
            features = keras.layers.Rescaling(1.0 / 255)(inputs)
            features = keras.layers.Conv2D(32, 3, activation='relu')(features)
            features = keras.layers.MaxPooling2D()(features)
            features = keras.layers.Conv2D(64, 3, activation='relu')(features)
            features = keras.layers.GlobalAveragePooling2D()(features)
            """
        ).strip(),
        "time_series": dedent(
            """
            features = keras.layers.LayerNormalization()(inputs)
            features = keras.layers.Dense(64, activation='relu')(features)
            """
        ).strip(),
    }[variant]
    input_line = {
        "classification": "inputs = keras.Input(shape=(FEATURE_DIM,), name='features')",
        "regression": "inputs = keras.Input(shape=(FEATURE_DIM,), name='features')",
        "nlp": "inputs = keras.Input(shape=(SEQUENCE_LENGTH,), dtype='int32', name='tokens')",
        "vision": "inputs = keras.Input(shape=(IMAGE_HEIGHT, IMAGE_WIDTH, 3), name='image')",
        "time_series": "inputs = keras.Input(shape=(WINDOW_SIZE,), name='window')",
    }[variant]
    model_content = "\n".join(
        [
            "import keras",
            "",
            "from .config import FEATURE_DIM, IMAGE_HEIGHT, IMAGE_WIDTH, NUM_CLASSES, SEQUENCE_LENGTH, VOCAB_SIZE, WINDOW_SIZE",
            "",
            "",
            "def build_model() -> keras.Model:",
            f"    {input_line}",
            indent(dedent(encoder).strip(), "    "),
            f"    outputs = {head}(features)",
            f'    model = keras.Model(inputs=inputs, outputs=outputs, name="{variant}_starter")',
            "    model.compile(",
            "        optimizer=keras.optimizers.Adam(),",
            f"        loss={loss},",
            f"        metrics={metrics},",
            "    )",
            "    return model",
        ]
    )
    data_builder = {
        "classification": dedent(
            """
            import tensorflow as tf

            from .config import BATCH_SIZE, FEATURE_DIM


            def build_datasets():
                train_ds = tf.data.Dataset.from_tensor_slices(
                    (tf.zeros((256, FEATURE_DIM), dtype=tf.float32), tf.zeros((256,), dtype=tf.int32))
                )
                val_ds = tf.data.Dataset.from_tensor_slices(
                    (tf.zeros((64, FEATURE_DIM), dtype=tf.float32), tf.zeros((64,), dtype=tf.int32))
                )
                train_ds = train_ds.shuffle(512).batch(BATCH_SIZE).prefetch(tf.data.AUTOTUNE)
                val_ds = val_ds.batch(BATCH_SIZE).prefetch(tf.data.AUTOTUNE)
                return train_ds, val_ds
            """
        ).strip(),
        "regression": dedent(
            """
            import tensorflow as tf

            from .config import BATCH_SIZE, FEATURE_DIM


            def build_datasets():
                train_ds = tf.data.Dataset.from_tensor_slices(
                    (tf.zeros((256, FEATURE_DIM), dtype=tf.float32), tf.zeros((256, 1), dtype=tf.float32))
                )
                val_ds = tf.data.Dataset.from_tensor_slices(
                    (tf.zeros((64, FEATURE_DIM), dtype=tf.float32), tf.zeros((64, 1), dtype=tf.float32))
                )
                train_ds = train_ds.shuffle(512).batch(BATCH_SIZE).prefetch(tf.data.AUTOTUNE)
                val_ds = val_ds.batch(BATCH_SIZE).prefetch(tf.data.AUTOTUNE)
                return train_ds, val_ds
            """
        ).strip(),
        "nlp": dedent(
            """
            import tensorflow as tf

            from .config import BATCH_SIZE, SEQUENCE_LENGTH


            def build_datasets():
                train_ds = tf.data.Dataset.from_tensor_slices(
                    (tf.zeros((256, SEQUENCE_LENGTH), dtype=tf.int32), tf.zeros((256,), dtype=tf.int32))
                )
                val_ds = tf.data.Dataset.from_tensor_slices(
                    (tf.zeros((64, SEQUENCE_LENGTH), dtype=tf.int32), tf.zeros((64,), dtype=tf.int32))
                )
                train_ds = train_ds.shuffle(512).batch(BATCH_SIZE).prefetch(tf.data.AUTOTUNE)
                val_ds = val_ds.batch(BATCH_SIZE).prefetch(tf.data.AUTOTUNE)
                return train_ds, val_ds
            """
        ).strip(),
        "vision": dedent(
            """
            import tensorflow as tf

            from .config import BATCH_SIZE, IMAGE_HEIGHT, IMAGE_WIDTH


            def build_datasets():
                train_ds = tf.data.Dataset.from_tensor_slices(
                    (
                        tf.zeros((256, IMAGE_HEIGHT, IMAGE_WIDTH, 3), dtype=tf.float32),
                        tf.zeros((256,), dtype=tf.int32),
                    )
                )
                val_ds = tf.data.Dataset.from_tensor_slices(
                    (
                        tf.zeros((64, IMAGE_HEIGHT, IMAGE_WIDTH, 3), dtype=tf.float32),
                        tf.zeros((64,), dtype=tf.int32),
                    )
                )
                train_ds = train_ds.shuffle(512).batch(BATCH_SIZE).prefetch(tf.data.AUTOTUNE)
                val_ds = val_ds.batch(BATCH_SIZE).prefetch(tf.data.AUTOTUNE)
                return train_ds, val_ds
            """
        ).strip(),
        "time_series": dedent(
            """
            import tensorflow as tf

            from .config import BATCH_SIZE, WINDOW_SIZE


            def build_datasets():
                train_ds = tf.data.Dataset.from_tensor_slices(
                    (tf.zeros((256, WINDOW_SIZE), dtype=tf.float32), tf.zeros((256, 1), dtype=tf.float32))
                )
                val_ds = tf.data.Dataset.from_tensor_slices(
                    (tf.zeros((64, WINDOW_SIZE), dtype=tf.float32), tf.zeros((64, 1), dtype=tf.float32))
                )
                train_ds = train_ds.shuffle(512).batch(BATCH_SIZE).prefetch(tf.data.AUTOTUNE)
                val_ds = val_ds.batch(BATCH_SIZE).prefetch(tf.data.AUTOTUNE)
                return train_ds, val_ds
            """
        ).strip(),
    }[variant]
    return _bundle(
        "keras_scaffold",
        variant,
        f"Keras {variant.replace('_', ' ')} starter",
        "A clean Keras 3 starter with separate config, data, model, and train entry points.",
        ["keras", "tensorflow"],
        {
            "tensorflow_starters/config.py": """
                FEATURE_DIM = 32
                NUM_CLASSES = 3
                BATCH_SIZE = 64
                EPOCHS = 10
                SEQUENCE_LENGTH = 128
                VOCAB_SIZE = 20000
                IMAGE_HEIGHT = 224
                IMAGE_WIDTH = 224
                WINDOW_SIZE = 96
            """,
            "tensorflow_starters/model.py": model_content,
            "tensorflow_starters/train.py": """
                from pathlib import Path

                import keras

                from .config import EPOCHS
                from .data import build_datasets
                from .model import build_model


                def main() -> None:
                    train_ds, val_ds = build_datasets()
                    model = build_model()
                    Path("artifacts").mkdir(parents=True, exist_ok=True)
                    callbacks = [
                        keras.callbacks.ModelCheckpoint("artifacts/best.keras", save_best_only=True),
                        keras.callbacks.TensorBoard(log_dir="artifacts/tensorboard"),
                    ]
                    model.fit(train_ds, validation_data=val_ds, epochs=EPOCHS, callbacks=callbacks)
                    model.save("artifacts/final.keras")


                if __name__ == "__main__":
                    main()
            """,
            "tensorflow_starters/data.py": data_builder,
        },
        [
            "python -m tensorflow_starters.train",
            "Verify artifacts/best.keras and artifacts/final.keras exist after training.",
            "Open the TensorBoard logdir before claiming the starter is product-shaped.",
        ],
        [
            "Saved .keras artifacts",
            "TensorBoard logs",
            "Validation metrics from model.fit()",
        ],
    )


def _tf_data_bundle(variant: str) -> TensorFlowFeatureBundle:
    builders = {
        "csv": "tf.data.experimental.make_csv_dataset('data/train.csv', batch_size=64, label_name='label', num_epochs=1)",
        "tfrecord": "tf.data.TFRecordDataset(tf.io.gfile.glob('data/*.tfrecord'))",
        "images": "keras.utils.image_dataset_from_directory('data/images', image_size=(224, 224), batch_size=32)",
        "text": "keras.utils.text_dataset_from_directory('data/text', batch_size=32)",
        "generator": "tf.data.Dataset.from_generator(generator_fn, output_signature=output_signature)",
    }
    if variant not in builders:
        raise ValueError(f"Unsupported tf.data variant `{variant}`.")
    source_code = builders[variant]
    already_batched = variant in {"csv", "images", "text"}
    return _bundle(
        "tf_data_pipeline",
        variant,
        f"tf.data {variant} pipeline",
        "A tf.data starter with batching, shuffling, caching, and prefetching already in place.",
        ["tensorflow", "keras"],
        {
            "tensorflow_starters/data_pipeline.py": f"""
                import tensorflow as tf
                import keras


                def generator_fn():
                    for _ in range(32):
                        yield tf.zeros((32,), dtype=tf.float32), tf.constant(0, dtype=tf.int32)


                output_signature = (
                    tf.TensorSpec(shape=(32,), dtype=tf.float32),
                    tf.TensorSpec(shape=(), dtype=tf.int32),
                )


                def build_dataset():
                    dataset = {source_code}
                    if isinstance(dataset, tuple):
                        dataset = dataset[0]
                    dataset = dataset.shuffle(1024)
                    dataset = dataset.cache()
                    dataset = dataset if {already_batched!r} else dataset.batch(64)
                    dataset = dataset.prefetch(tf.data.AUTOTUNE)
                    return dataset
            """,
            "tensorflow_starters/data_validation.py": """
                import tensorflow as tf


                def inspect_element_spec(dataset: tf.data.Dataset) -> dict[str, str]:
                    return {key: str(value) for key, value in dataset.element_spec._asdict().items()} if hasattr(dataset.element_spec, "_asdict") else {"spec": str(dataset.element_spec)}
            """,
        },
        [
            "Build the dataset and print element_spec before wiring it into the model.",
            "Confirm shuffle, cache, batch, and prefetch are present in the final pipeline.",
        ],
        [
            "Dataset element_spec",
            "Pipeline throughput notes",
            "Any schema or shape mismatches found before training",
        ],
    )


def _finetuning_bundle(variant: str) -> TensorFlowFeatureBundle:
    hub_url = {
        "image_classifier": "https://tfhub.dev/google/imagenet/mobilenet_v2_100_224/feature_vector/5",
        "text_encoder": "https://tfhub.dev/google/nnlm-en-dim50/2",
    }.get(variant)
    if hub_url is None:
        raise ValueError(f"Unsupported fine-tuning variant `{variant}`.")
    input_line = "keras.Input(shape=(224, 224, 3), name='image')" if variant == "image_classifier" else "keras.Input(shape=(), dtype=tf.string, name='text')"
    return _bundle(
        "pretrained_finetuning",
        variant,
        f"TF Hub {variant.replace('_', ' ')} fine-tuning starter",
        "A transfer-learning starter that keeps baseline, frozen-layer, and fine-tune phases explicit.",
        ["tensorflow", "keras", "tensorflow_hub"],
        {
            "tensorflow_starters/finetune.py": f"""
                import keras
                import tensorflow as tf
                import tensorflow_hub as hub


                def build_model(num_classes: int = 3) -> keras.Model:
                    inputs = {input_line}
                    backbone = hub.KerasLayer("{hub_url}", name="hub_backbone")
                    backbone.trainable = False
                    features = backbone(inputs)
                    outputs = keras.layers.Dense(num_classes, activation="softmax")(features)
                    model = keras.Model(inputs, outputs)
                    model.compile(
                        optimizer=keras.optimizers.Adam(1e-3),
                        loss=keras.losses.SparseCategoricalCrossentropy(),
                        metrics=["accuracy"],
                    )
                    return model


                def unfreeze_for_finetune(model: keras.Model) -> None:
                    model.get_layer("hub_backbone").trainable = True
                    model.compile(
                        optimizer=keras.optimizers.Adam(1e-5),
                        loss=keras.losses.SparseCategoricalCrossentropy(),
                        metrics=["accuracy"],
                    )
            """,
            "tensorflow_starters/baseline_eval.py": """
                def baseline_metrics() -> dict[str, float]:
                    return {"accuracy": 0.0}
            """,
        },
        [
            "Run a frozen-backbone baseline before unfreezing any layers.",
            "Compare baseline and fine-tuned metrics before claiming transfer learning helped.",
        ],
        [
            "Baseline metrics",
            "Fine-tuned metrics",
            "Layer-freeze versus unfreeze configuration",
        ],
    )


def _training_loop_bundle(variant: str) -> TensorFlowFeatureBundle:
    if variant == "model_fit":
        files = {
            "tensorflow_starters/train_loop.py": """
                import keras


                def run_training(model, train_ds, val_ds):
                    callbacks = [keras.callbacks.EarlyStopping(patience=3, restore_best_weights=True)]
                    return model.fit(train_ds, validation_data=val_ds, epochs=20, callbacks=callbacks)
            """,
        }
    elif variant == "custom_gradient_tape":
        files = {
            "tensorflow_starters/custom_loop.py": """
                import tensorflow as tf


                @tf.function
                def train_step(model, optimizer, loss_fn, features, labels):
                    with tf.GradientTape() as tape:
                        predictions = model(features, training=True)
                        loss = loss_fn(labels, predictions)
                    gradients = tape.gradient(loss, model.trainable_variables)
                    optimizer.apply_gradients(zip(gradients, model.trainable_variables))
                    return loss
            """,
        }
    else:
        raise ValueError(f"Unsupported training-loop variant `{variant}`.")
    return _bundle(
        "training_loop",
        variant,
        f"Training loop: {variant.replace('_', ' ')}",
        "A starter for either high-level Keras training or lower-level custom loops.",
        ["tensorflow", "keras"],
        files,
        [
            "Run a single epoch sanity check before longer training.",
            "Capture loss and validation behavior after the first run.",
        ],
        [
            "Training history or step metrics",
            "Clear evidence whether fit() or the custom loop was used",
        ],
    )


def _distributed_bundle(variant: str) -> TensorFlowFeatureBundle:
    if variant == "mirrored":
        content = """
            import tensorflow as tf


            strategy = tf.distribute.MirroredStrategy()
            with strategy.scope():
                model = build_model()
        """
    elif variant == "multi_worker":
        content = """
            import json
            import os
            import tensorflow as tf


            os.environ.setdefault("TF_CONFIG", json.dumps({
                "cluster": {"worker": ["host0:12345", "host1:12345"]},
                "task": {"type": "worker", "index": 0},
            }))
            strategy = tf.distribute.MultiWorkerMirroredStrategy()
            with strategy.scope():
                model = build_model()
        """
    else:
        raise ValueError(f"Unsupported distributed-training variant `{variant}`.")
    return _bundle(
        "distributed_training",
        variant,
        f"Distributed training: {variant.replace('_', ' ')}",
        "A distribution starter for either single-node multi-GPU or multi-worker setups.",
        ["tensorflow", "keras"],
        {
            "tensorflow_starters/distribute.py": (
                "from .model import build_model\n\n" + dedent(content).strip() + "\n"
            )
        },
        [
            "Verify device visibility before starting distributed training.",
            "Run a tiny smoke epoch before trusting the cluster-scale configuration.",
        ],
        [
            "Visible device list",
            "Strategy type used for the training run",
        ],
    )


def _tensorboard_bundle(_variant: str) -> TensorFlowFeatureBundle:
    return _bundle(
        "tensorboard_observability",
        "default",
        "TensorBoard observability starter",
        "Auto-wire TensorBoard callbacks, profiling, and run-comparison conventions.",
        ["tensorflow", "keras", "tensorboard"],
        {
            "tensorflow_starters/observability.py": """
                from pathlib import Path

                import keras
                import tensorflow as tf


                def training_callbacks(run_name: str = "baseline"):
                    Path(f"artifacts/tensorboard/{run_name}").mkdir(parents=True, exist_ok=True)
                    Path("artifacts/metrics").mkdir(parents=True, exist_ok=True)
                    return [
                        keras.callbacks.TensorBoard(
                            log_dir=f"artifacts/tensorboard/{run_name}",
                            histogram_freq=1,
                            write_graph=True,
                            profile_batch="20,30",
                        ),
                        keras.callbacks.CSVLogger(f"artifacts/metrics/{run_name}.csv"),
                    ]
            """,
            "tensorflow_starters/compare_runs.md": """
                # TensorBoard run comparison

                - Keep each run under `artifacts/tensorboard/<run_name>`.
                - Compare baseline, tuned, and export-safe runs in the same dashboard.
                - Do not claim training improved if the baseline run is missing.
            """,
        },
        [
            "Launch tensorboard --logdir artifacts/tensorboard",
            "Compare at least two named runs before summarizing training changes.",
        ],
        [
            "TensorBoard logs",
            "CSV metrics per run",
            "Profile traces for at least one representative step range",
        ],
    )


def _tuning_bundle(variant: str) -> TensorFlowFeatureBundle:
    tuner_class = {
        "random_search": "keras_tuner.RandomSearch",
        "bayesian_optimization": "keras_tuner.BayesianOptimization",
        "hyperband": "keras_tuner.Hyperband",
    }.get(variant)
    if tuner_class is None:
        raise ValueError(f"Unsupported tuning variant `{variant}`.")
    tuner_args = {
        "random_search": ["max_trials=12,", 'directory="artifacts/tuning",', 'project_name="random_search",'],
        "bayesian_optimization": ["max_trials=12,", 'directory="artifacts/tuning",', 'project_name="bayesian_optimization",'],
        "hyperband": ["max_epochs=12,", "factor=3,", 'directory="artifacts/tuning",', 'project_name="hyperband",'],
    }[variant]
    tune_content = "\n".join(
        [
            "import keras",
            "import keras_tuner",
            "",
            "",
            "def build_model(hp):",
            "    model = keras.Sequential([",
            '        keras.layers.Input(shape=(32,)),',
            '        keras.layers.Dense(hp.Int("units", min_value=64, max_value=256, step=64), activation="relu"),',
            '        keras.layers.Dense(3, activation="softmax"),',
            "    ])",
            "    model.compile(",
            '        optimizer=keras.optimizers.Adam(hp.Float("learning_rate", 1e-4, 1e-2, sampling="log")),',
            "        loss=keras.losses.SparseCategoricalCrossentropy(),",
            '        metrics=["accuracy"],',
            "    )",
            "    return model",
            "",
            "",
            "def build_tuner():",
            f"    return {tuner_class}(",
            "        build_model,",
            '        objective="val_accuracy",',
            *[f"        {line}" for line in tuner_args],
            "    )",
        ]
    )
    return _bundle(
        "hyperparameter_tuning",
        variant,
        f"KerasTuner {variant.replace('_', ' ')} starter",
        "A bounded tuning recipe with a named search strategy and explicit result export.",
        ["tensorflow", "keras", "keras_tuner"],
        {
            "tensorflow_starters/tune.py": tune_content,
        },
        [
            "Run the tuner with an explicit max_trials or epoch budget.",
            "Compare the best trial against the untuned baseline before recommending it.",
        ],
        [
            "Best hyperparameters",
            "Baseline versus tuned metrics",
            "The tuning budget actually used",
        ],
    )


def _export_bundle(_variant: str) -> TensorFlowFeatureBundle:
    return _bundle(
        "model_export_guardrails",
        "savedmodel_and_keras",
        "Model export guardrails",
        "Separate Keras training checkpoints from exported inference artifacts with explicit signatures.",
        ["tensorflow", "keras"],
        {
            "tensorflow_starters/export.py": """
                from pathlib import Path

                import keras
                import tensorflow as tf


                def save_training_artifact(model: keras.Model) -> None:
                    Path("artifacts").mkdir(parents=True, exist_ok=True)
                    model.save("artifacts/model.keras")


                def build_serving_signature(model: keras.Model):
                    @tf.function(input_signature=[tf.TensorSpec(shape=[None, 32], dtype=tf.float32, name="features")])
                    def serve_fn(features):
                        return {"predictions": model(features, training=False)}

                    return serve_fn


                def export_inference_artifact(model: keras.Model) -> None:
                    Path("artifacts").mkdir(parents=True, exist_ok=True)
                    signature = build_serving_signature(model)
                    tf.saved_model.save(model, "artifacts/exported_model", signatures={"serving_default": signature})
            """,
            "tensorflow_starters/export_contract.md": """
                # Export contract

                - `.keras` is for training-time restore and iteration.
                - `artifacts/exported_model` is the serving artifact.
                - Keep the serving signature explicit so inference callers do not reverse-engineer tensor names.
            """,
        },
        [
            "Verify both artifacts/model.keras and artifacts/exported_model exist.",
            "Inspect the serving signature before claiming the model is deployable.",
        ],
        [
            "Separate training and serving artifact paths",
            "Explicit inference signature",
        ],
    )


def _serving_bundle(_variant: str) -> TensorFlowFeatureBundle:
    return _bundle(
        "serving_api",
        "tensorflow_serving_fastapi",
        "TensorFlow Serving plus API wrapper",
        "A serving scaffold with TensorFlow Serving model config and a thin HTTP wrapper.",
        ["tensorflow", "fastapi", "uvicorn", "requests"],
        {
            "tensorflow_starters/serving/models.config": """
                model_config_list: {
                  config: {
                    name: "starter_model",
                    base_path: "/models/starter_model",
                    model_platform: "tensorflow"
                  }
                }
            """,
            "tensorflow_starters/serving/api.py": """
                import requests
                from fastapi import FastAPI


                app = FastAPI()
                TF_SERVING_URL = "http://localhost:8501/v1/models/starter_model:predict"


                @app.post("/predict")
                def predict(payload: dict) -> dict:
                    response = requests.post(TF_SERVING_URL, json=payload, timeout=10)
                    response.raise_for_status()
                    return response.json()
            """,
        },
        [
            "Start TensorFlow Serving with the generated model config.",
            "Call the FastAPI wrapper and compare its payload contract with the serving signature.",
        ],
        [
            "Serving config path",
            "Working inference request/response example",
        ],
    )


def _tfx_bundle(_variant: str) -> TensorFlowFeatureBundle:
    return _bundle(
        "tfx_pipeline",
        "end_to_end",
        "TFX end-to-end pipeline starter",
        "A TFX skeleton with ingestion, validation, transform, training, tuning, evaluation, infra validation, and push stages.",
        ["tensorflow", "tfx", "tensorflow_data_validation", "tensorflow_transform", "tensorflow_model_analysis"],
        {
            "tensorflow_starters/tfx_pipeline.py": """
                from tfx import v1 as tfx
                import tensorflow_model_analysis as tfma


                def create_pipeline(pipeline_root: str, data_root: str, serving_model_dir: str):
                    example_gen = tfx.components.CsvExampleGen(input_base=data_root)
                    statistics_gen = tfx.components.StatisticsGen(examples=example_gen.outputs["examples"])
                    schema_gen = tfx.components.SchemaGen(statistics=statistics_gen.outputs["statistics"], infer_feature_shape=True)
                    example_validator = tfx.components.ExampleValidator(
                        statistics=statistics_gen.outputs["statistics"],
                        schema=schema_gen.outputs["schema"],
                    )
                    transform = tfx.components.Transform(
                        examples=example_gen.outputs["examples"],
                        schema=schema_gen.outputs["schema"],
                        module_file="tensorflow_starters/preprocessing.py",
                    )
                    tuner = tfx.components.Tuner(
                        module_file="tensorflow_starters/trainer.py",
                        examples=transform.outputs["transformed_examples"],
                        transform_graph=transform.outputs["transform_graph"],
                        train_args=tfx.proto.TrainArgs(num_steps=500),
                        eval_args=tfx.proto.EvalArgs(num_steps=100),
                    )
                    trainer = tfx.components.Trainer(
                        module_file="tensorflow_starters/trainer.py",
                        examples=transform.outputs["transformed_examples"],
                        transform_graph=transform.outputs["transform_graph"],
                        schema=schema_gen.outputs["schema"],
                        train_args=tfx.proto.TrainArgs(num_steps=500),
                        eval_args=tfx.proto.EvalArgs(num_steps=100),
                    )
                    eval_config = tfma.EvalConfig(
                        model_specs=[tfma.ModelSpec(label_key="label")],
                        slicing_specs=[tfma.SlicingSpec(), tfma.SlicingSpec(feature_keys=["segment"])],
                    )
                    evaluator = tfx.components.Evaluator(
                        examples=example_gen.outputs["examples"],
                        model=trainer.outputs["model"],
                        eval_config=eval_config,
                    )
                    infra_validator = tfx.components.InfraValidator(
                        model=trainer.outputs["model"],
                        examples=example_gen.outputs["examples"],
                    )
                    pusher = tfx.components.Pusher(
                        model=trainer.outputs["model"],
                        push_destination=tfx.proto.PushDestination(
                            filesystem=tfx.proto.PushDestination.Filesystem(base_directory=serving_model_dir)
                        ),
                    )
                    return tfx.dsl.Pipeline(
                        pipeline_name="starter_pipeline",
                        pipeline_root=pipeline_root,
                        components=[
                            example_gen,
                            statistics_gen,
                            schema_gen,
                            example_validator,
                            transform,
                            tuner,
                            trainer,
                            evaluator,
                            infra_validator,
                            pusher,
                        ],
                    )
            """,
            "tensorflow_starters/trainer.py": """
                import keras


                def run_fn(fn_args):
                    model = keras.Sequential([
                        keras.layers.Input(shape=(32,)),
                        keras.layers.Dense(32, activation="relu"),
                        keras.layers.Dense(3, activation="softmax"),
                    ])
                    model.compile(
                        optimizer=keras.optimizers.Adam(),
                        loss=keras.losses.SparseCategoricalCrossentropy(),
                        metrics=["accuracy"],
                    )
                    model.export(fn_args.serving_model_dir)
            """,
            "tensorflow_starters/preprocessing.py": """
                def preprocessing_fn(inputs):
                    return inputs
            """,
        },
        [
            "Validate the pipeline compiles before running it.",
            "Check schema, transform, trainer, evaluator, infra validator, and pusher stages separately.",
        ],
        [
            "Per-component pipeline status",
            "Evaluation and infra validation outcomes",
        ],
    )


def _data_validation_bundle(_variant: str) -> TensorFlowFeatureBundle:
    return _bundle(
        "data_validation",
        "tfdv_schema",
        "TensorFlow data validation starter",
        "A schema and anomaly-check starter that catches drift before training.",
        ["tensorflow_data_validation"],
        {
            "tensorflow_starters/data_validation.py": """
                import tensorflow_data_validation as tfdv


                def validate_stats(train_path: str, serving_path: str):
                    train_stats = tfdv.generate_statistics_from_csv(data_location=train_path)
                    schema = tfdv.infer_schema(statistics=train_stats)
                    serving_stats = tfdv.generate_statistics_from_csv(data_location=serving_path)
                    anomalies = tfdv.validate_statistics(statistics=serving_stats, schema=schema)
                    return train_stats, schema, anomalies
            """,
        },
        [
            "Generate baseline dataset statistics before training.",
            "Validate serving or fresh input statistics against the baseline schema.",
        ],
        [
            "Schema artifact",
            "Anomaly report",
            "Feature drift summary",
        ],
    )


def _skew_prevention_bundle(_variant: str) -> TensorFlowFeatureBundle:
    return _bundle(
        "skew_prevention",
        "tensorflow_transform",
        "Training/serving skew prevention starter",
        "A preprocessing template that uses TensorFlow Transform-style logic for both training and inference.",
        ["tensorflow_transform", "tensorflow"],
        {
            "tensorflow_starters/preprocessing.py": """
                import tensorflow_transform as tft


                def preprocessing_fn(inputs):
                    outputs = {}
                    outputs["age_xf"] = tft.scale_to_z_score(inputs["age"])
                    outputs["country_xf"] = tft.compute_and_apply_vocabulary(inputs["country"])
                    outputs["label"] = inputs["label"]
                    return outputs
            """,
            "tensorflow_starters/trainer.py": """
                def transformed_feature_spec():
                    return {
                        "age_xf": "float32",
                        "country_xf": "int64",
                        "label": "int64",
                    }
            """,
        },
        [
            "Verify training uses the transform graph rather than raw-feature ad hoc preprocessing.",
            "Verify serving reads the same transformed feature contract.",
        ],
        [
            "Transform graph artifact",
            "Shared preprocessing function used for both training and serving",
        ],
    )


def _slice_eval_bundle(_variant: str) -> TensorFlowFeatureBundle:
    return _bundle(
        "evaluation_by_slice",
        "tfma_slices",
        "Slice-aware evaluation starter",
        "A TFMA evaluation config that keeps slice quality visible.",
        ["tensorflow_model_analysis"],
        {
            "tensorflow_starters/eval_config.py": """
                import tensorflow_model_analysis as tfma


                def build_eval_config():
                    return tfma.EvalConfig(
                        model_specs=[tfma.ModelSpec(label_key="label")],
                        metrics_specs=[tfma.MetricsSpec(metrics=[tfma.MetricConfig(class_name="SparseCategoricalAccuracy")])],
                        slicing_specs=[
                            tfma.SlicingSpec(),
                            tfma.SlicingSpec(feature_keys=["segment"]),
                            tfma.SlicingSpec(feature_keys=["country"]),
                        ],
                    )
            """,
        },
        [
            "Evaluate at least one important product segment in addition to the global slice.",
            "Do not ship if one slice quietly collapses while the aggregate metric smiles at you.",
        ],
        [
            "Per-slice evaluation report",
            "Aggregate versus slice metric comparison",
        ],
    )


def _tflite_bundle(_variant: str) -> TensorFlowFeatureBundle:
    return _bundle(
        "on_device_deployment",
        "tflite_mobile",
        "TensorFlow Lite deployment starter",
        "A TFLite conversion starter with mobile integration and representative-dataset hooks.",
        ["tensorflow"],
        {
            "tensorflow_starters/tflite_export.py": """
                from pathlib import Path

                import tensorflow as tf


                def representative_dataset():
                    for _ in range(100):
                        yield [tf.random.uniform((1, 32), dtype=tf.float32)]


                def export_tflite(saved_model_dir: str, output_path: str) -> None:
                    converter = tf.lite.TFLiteConverter.from_saved_model(saved_model_dir)
                    converter.optimizations = [tf.lite.Optimize.DEFAULT]
                    converter.representative_dataset = representative_dataset
                    tflite_model = converter.convert()
                    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                    with open(output_path, "wb") as handle:
                        handle.write(tflite_model)
            """,
            "tensorflow_starters/mobile_integration.kt": """
                // Kotlin integration sketch
                import java.nio.MappedByteBuffer
                import org.tensorflow.lite.Interpreter


                fun loadModelFile(name: String): MappedByteBuffer {
                    TODO("Provide an asset-backed model file loader for your Android app.")
                }

                val options = Interpreter.Options()
                val interpreter = Interpreter(loadModelFile("model.tflite"), options)
            """,
        },
        [
            "Export the .tflite artifact from a known SavedModel directory.",
            "Validate size, latency, and representative-input compatibility before claiming edge readiness.",
        ],
        [
            ".tflite artifact path",
            "Representative dataset configuration",
            "Device constraint notes",
        ],
    )


def _optimization_bundle(_variant: str) -> TensorFlowFeatureBundle:
    return _bundle(
        "optimization_advisor",
        "mobile_edge",
        "Edge optimization advisor",
        "A deployment-aware optimization starter with quantization and pruning guidance.",
        ["tensorflow", "tensorflow_model_optimization"],
        {
            "tensorflow_starters/optimization_advisor.md": """
                # TensorFlow edge optimization advisor

                1. Start with a baseline for size, latency, memory, and quality.
                2. Try dynamic-range quantization first when accuracy risk must stay low.
                3. Use full integer quantization when the target requires smaller or faster inference and you have a representative dataset.
                4. Consider pruning only when model size matters and retraining cost is acceptable.
                5. Re-check TensorFlow Lite export and slice metrics after every optimization step.
            """,
            "tensorflow_starters/quantize.py": """
                from pathlib import Path

                import tensorflow as tf


                def quantize_saved_model(saved_model_dir: str, output_path: str) -> None:
                    converter = tf.lite.TFLiteConverter.from_saved_model(saved_model_dir)
                    converter.optimizations = [tf.lite.Optimize.DEFAULT]
                    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                    with open(output_path, "wb") as handle:
                        handle.write(converter.convert())
            """,
        },
        [
            "Record the baseline artifact size and latency before optimization.",
            "Compare optimized and baseline outputs before recommending the optimized model.",
        ],
        [
            "Baseline versus optimized artifact size",
            "Latency and memory comparison",
            "Post-optimization accuracy or slice-evaluation results",
        ],
    )
