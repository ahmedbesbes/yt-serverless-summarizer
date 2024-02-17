import email
import os
from pulumi import asset, export, info
import pulumi_gcp as gcp
from dotenv import load_dotenv

load_dotenv()

bucket = gcp.storage.Bucket("bucket", location="EU")

archive = gcp.storage.BucketObject(
    "python-zip",
    bucket=bucket.name,
    source=asset.AssetArchive({".": asset.FileArchive("./function")}),
)

secret = gcp.secretmanager.Secret(
    "openai-api-key",
    replication=gcp.secretmanager.SecretReplicationArgs(
        auto=gcp.secretmanager.SecretReplicationAutoArgs(),
    ),
    secret_id="openai-secret",
)
secret_version = gcp.secretmanager.SecretVersion(
    "1",
    secret=secret.name,
    secret_data=os.environ.get("OPENAI_API_KEY"),
)


service_account = gcp.serviceaccount.Account(
    "service-account",
    account_id="service-account-id",
    display_name="Summarizer Service Account",
)


service_account_email = service_account.email.apply(
    lambda email: f"serviceAccount:{email}"
)

secret_accessor = gcp.organizations.get_iam_policy(
    bindings=[
        gcp.organizations.GetIAMPolicyBindingArgs(
            role="roles/secretmanager.secretAccessor",
            members=[service_account_email],
        )
    ]
)

secret_iam_policy = gcp.secretmanager.SecretIamPolicy(
    "my-secret-iam-policy",
    secret_id=secret.id,
    project=gcp.config.project,
    policy_data=secret_accessor.policy_data,
)


cloud_function = gcp.cloudfunctionsv2.Function(
    resource_name="cloud-function",
    location="europe-west1",
    build_config=gcp.cloudfunctionsv2.FunctionBuildConfigArgs(
        entry_point="main",
        runtime="python39",
        source=gcp.cloudfunctionsv2.FunctionBuildConfigSourceArgs(
            storage_source=gcp.cloudfunctionsv2.FunctionBuildConfigSourceStorageSourceArgs(
                bucket=bucket.name,
                object=archive.name,
            )
        ),
    ),
    service_config=gcp.cloudfunctionsv2.FunctionServiceConfigArgs(
        available_memory="256M",
        ingress_settings="ALLOW_ALL",
        timeout_seconds=60,
        service_account_email=service_account.email,
        secret_environment_variables=[
            gcp.cloudfunctionsv2.FunctionServiceConfigSecretEnvironmentVariableArgs(
                key="OPENAI_API_KEY",
                version="1",
                project_id=gcp.config.project,
                secret="openai-secret",
            )
        ],
    ),
)

binding = gcp.cloudrun.IamBinding(
    "binding",
    location=cloud_function.location,
    service=cloud_function.name,
    role="roles/run.invoker",
    members=["allUsers"],
)

export("python_endpoint", cloud_function.service_config.apply(lambda sc: sc.uri))
