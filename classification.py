# python3 -m pip install "kfp<2.0.0" "google-cloud-aiplatform>=1.16.0" --upgrade --quiet

from kfp import components
from kfp.v2 import dsl
from google.cloud import aiplatform
from kfp.v2 import compiler

# %% Loading components
upload_Tensorflow_model_to_Google_Cloud_Vertex_AI_op = components.load_component_from_url(
    'https://raw.githubusercontent.com/GoogleCloudPlatform/vertex-ai-samples/399405402d95f4a011e2d2e967c96f8508ba5688/community-content/pipeline_components/google-cloud/Vertex_AI/Models/Upload_Tensorflow_model/component.yaml'
)
deploy_model_to_endpoint_op = components.load_component_from_url(
    'https://raw.githubusercontent.com/GoogleCloudPlatform/vertex-ai-samples/399405402d95f4a011e2d2e967c96f8508ba5688/community-content/pipeline_components/google-cloud/Vertex_AI/Models/Deploy_to_endpoint/component.yaml'
)
transcode_imagedataset_tfrecord_from_csv_op = components.load_component_from_url(
    'https://raw.githubusercontent.com/GoogleCloudPlatform/vertex-ai-samples/main/community-content/pipeline_components/image_ml_model_training/transcode_tfrecord_image_dataset_from_csv/component.yaml'
)
load_image_classification_model_from_tfhub_op = components.load_component_from_url(
    'https://raw.githubusercontent.com/GoogleCloudPlatform/vertex-ai-samples/b5b65198a6c2ffe8c0fa2aa70127e3325752df68/community-content/pipeline_components/image_ml_model_training/load_image_classification_model/component.yaml'
)
preprocess_image_data_op = components.load_component_from_url(
    'https://raw.githubusercontent.com/GoogleCloudPlatform/vertex-ai-samples/main/community-content/pipeline_components/image_ml_model_training/preprocess_image_data/component.yaml'
)
train_tensorflow_image_classification_model_op = components.load_component_from_url(
    'https://raw.githubusercontent.com/GoogleCloudPlatform/vertex-ai-samples/main/community-content/pipeline_components/image_ml_model_training/train_image_classification_model/component.yaml'
)

# %% Pipeline definition
@dsl.pipeline(
    name="image-classification-pipeline",
    description="Pipeline to train and optionally deploy image classification model"
)
def image_classification_pipeline(
    deploy_model: bool = False  # now a parameter, so it can be used in dsl.Condition
):
    class_names = ['daisy', 'dandelion', 'roses', 'sunflowers', 'tulips']
    csv_image_data_path = 'gs://cloud-samples-data/ai-platform/flowers/flowers.csv'

    image_data = dsl.importer(
        artifact_uri=csv_image_data_path,
        artifact_class=dsl.Dataset,
        metadata={'data_format': 'csv'}
    ).output

    image_tfrecord_data = transcode_imagedataset_tfrecord_from_csv_op(
        csv_image_data_path=image_data,
        class_names=class_names
    ).outputs['tfrecord_image_data_path']

    loaded_model_outputs = load_image_classification_model_from_tfhub_op(
        class_names=class_names,
    ).outputs

    preprocessed_data = preprocess_image_data_op(
        image_tfrecord_data,
        height_width_path=loaded_model_outputs['image_size_path'],
    ).outputs

    trained_model = train_tensorflow_image_classification_model_op(
        preprocessed_training_data_path=preprocessed_data['preprocessed_training_data_path'],
        preprocessed_validation_data_path=preprocessed_data['preprocessed_validation_data_path'],
        model_path=loaded_model_outputs['loaded_model_path']
    ).set_cpu_limit('96').set_memory_limit('128G').add_node_selector_constraint(
        'cloud.google.com/gke-accelerator', 'NVIDIA_TESLA_A100'
    ).set_gpu_limit('8').outputs['trained_model_path']

    vertex_model_name = upload_Tensorflow_model_to_Google_Cloud_Vertex_AI_op(
        model=trained_model,
    ).outputs['model_name']

    with dsl.Condition(deploy_model == True):
        deploy_model_to_endpoint_op(model_name=vertex_model_name)

# %% Compile and Submit Pipeline
if __name__ == '__main__':
    project = 'boxwood-pillar-460900-j5'
    region = 'us-east1'
    pipeline_filename = 'image_classification_pipeline.json'

    compiler.Compiler().compile(
        pipeline_func=image_classification_pipeline,
        package_path=pipeline_filename
    )

    aiplatform.init(project=project, location=region)

    job = aiplatform.PipelineJob(
        display_name='image-classification-job',
        template_path=pipeline_filename
    )
    job.run()
