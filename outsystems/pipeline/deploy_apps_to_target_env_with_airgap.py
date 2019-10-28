# Python Modules
import sys
import os
import argparse
from pkg_resources import parse_version
from time import sleep

# Workaround for Jenkins:
# Set the path to include the outsystems module
# Jenkins exposes the workspace directory through env.
if "WORKSPACE" in os.environ:
    sys.path.append(os.environ['WORKSPACE'])
else:  # Else just add the project dir
    sys.path.append(os.getcwd())

# Custom Modules
# Variables
from outsystems.vars.file_vars import ARTIFACT_FOLDER, DEPLOYMENT_FOLDER, DEPLOYMENT_MANIFEST_FILE, APPLICATION_OAP_FOLDER, APPLICATION_OAP_FILE
from outsystems.vars.lifetime_vars import LIFETIME_HTTP_PROTO, LIFETIME_API_ENDPOINT, LIFETIME_API_VERSION, DEPLOYMENT_MESSAGE
from outsystems.vars.pipeline_vars import QUEUE_TIMEOUT_IN_SECS, SLEEP_PERIOD_IN_SECS, CONFLICTS_FILE, \
    REDEPLOY_OUTDATED_APPS, DEPLOYMENT_TIMEOUT_IN_SECS, DEPLOYMENT_RUNNING_STATUS, DEPLOYMENT_WAITING_STATUS, \
    DEPLOYMENT_ERROR_STATUS_LIST, DEPLOY_ERROR_FILE
from outsystems.vars.cicd_vars import PROBE_HTTP_PROTO, PROBE_API_ENDPOINT, PROBE_API_VERSION

# Functions
from outsystems.lifetime.lifetime_environments import get_environment_app_version, get_environment_key
from outsystems.lifetime.lifetime_applications import get_running_app_version, get_application_version, export_app_oap
from outsystems.lifetime.lifetime_deployments import get_deployment_status, get_deployment_info, \
    send_deployment, delete_deployment, start_deployment, continue_deployment, get_running_deployment
from outsystems.file_helpers.file import store_data, load_data
from outsystems.lifetime.lifetime_base import build_lt_endpoint
from outsystems.cicd_probe.cicd_base import build_probe_endpoint
from outsystems.osp_tool.osp_base import deploy_app_oap
from outsystems.cicd_probe.cicd_dependencies import get_app_dependencies, sort_app_dependencies
from outsystems.pipeline.deploy_latest_tags_to_target_env import generate_deployment_based_on_manifest, generate_regular_deployment

# Exceptions
from outsystems.exceptions.no_deployments import NoDeploymentsError
from outsystems.exceptions.app_does_not_exist import AppDoesNotExistError

############################################################## SCRIPT ##############################################################

# TODO comment the new functions
#  Exports the OAP files of a given list of aplications


def generate_oap_list(app_data_list :list):
    app_oap_list = []
    for app in app_data_list:
        filename = "{}{}".format(app["VersionKey"], APPLICATION_OAP_FILE)
        app_oap_list.append({"app_name": app["Name"], "app_version": app["Version"], "app_key": app["Key"], "version_key": app["VersionKey"], "filename": filename})
        print("{} application with version {}, to be exported as {}".format(app["Name"], app["Version"], filename))
    return app_oap_list


def export_apps_oap(artifact_dir :str, lt_endpoint: str, lt_token: str, env_key :str, env_name :str, app_oap_list :list):
    for app in app_oap_list:
        file_path = os.path.join(artifact_dir, APPLICATION_OAP_FOLDER, app["filename"])
        export_app_oap(file_path, lt_endpoint, lt_token, env_key, app_key=app["app_key"], app_version_key=app["version_key"])

def generate_deployment_order(artifact_dir :str, probe_endpoint: str, app_oap_list: list):
    dependencies_list = {}

    for app in app_oap_list:
        dependencies_list[app["app_key"]] = get_app_dependencies(artifact_dir, probe_endpoint, app["version_key"], app["app_name"], app["app_version"])

    dependencies_order_list = sort_app_dependencies(dependencies_list)

    final_list = []
    for app_dep in dependencies_order_list:
        for app_oap in app_oap_list:
            if app_dep == app_oap["app_key"]:
                final_list.append(app_oap)

    return final_list

def deploy_apps_oap(artifact_dir :str, dest_env: str, osp_tool_path: str, credentials: str, app_oap_list: list):
    for app in app_oap_list:
        oap_file_path = os.path.join(artifact_dir, APPLICATION_OAP_FOLDER, app["filename"])
        deploy_app_oap(osp_tool_path, oap_file_path, dest_env, credentials)

def main(artifact_dir: str, lt_http_proto: str, lt_url: str, lt_api_endpoint: str, lt_api_version: int, lt_token: str, source_env: str, dest_env: str, apps: list, dep_manifest :list, dep_note: str, osp_tool_path: str, credentials: str, cicd_http_proto: str, cicd_url: str, cicd_api_endpoint: str, cicd_version: str):

    app_data_list = []  # will contain the applications to deploy details from LT
    to_deploy_app_keys = []  # will contain the app keys for the apps tagged

    # Builds the LifeTime endpoint
    lt_endpoint = build_lt_endpoint(lt_http_proto, lt_url, lt_api_endpoint, lt_api_version)
    # Builds the Probe endpoint
    probe_endpoint = build_probe_endpoint(cicd_http_proto, cicd_url, cicd_api_endpoint, cicd_version)

    # Gets the environment key for the source environment
    src_env_key = get_environment_key(artifact_dir, lt_endpoint, lt_token, source_env)

    # If the manifest file is being used, the app versions MUST come from that file
    # Or else you might not be deploying the same app versions that were deployed in
    # previous pipeline steps
    if dep_manifest:
        app_data_list = generate_deployment_based_on_manifest(artifact_dir, lt_endpoint, lt_token, src_env_key, source_env, apps, dep_manifest)
    else:
        app_data_list = generate_regular_deployment(artifact_dir, lt_endpoint, lt_token, src_env_key, apps)


    app_oap_list = generate_oap_list(app_data_list)
    export_apps_oap(artifact_dir, lt_endpoint, lt_token, src_env_key, source_env, app_oap_list)

    sorted_oap_list = generate_deployment_order(artifact_dir, probe_endpoint, app_oap_list)

    deploy_res = ""
    for oap in sorted_oap_list:
        if sorted_oap_list.index(oap) == 0:
            deploy_res = "      " + str(sorted_oap_list.index(oap)) + ". " + oap["app_name"] +"("+ oap["version_key"]+")\n"
        else:     
            deploy_res =  deploy_res + "      " + str(sorted_oap_list.index(oap)) + ". " + oap["app_name"] +"("+ oap["version_key"]+")\n"

    print("\nDeployment Order:\n{}".format(deploy_res))   

     #deploy_apps_oap(artifact_dir, dest_env, osp_tool_path, credentials, sorted_oap_list)
 

# End of main()


if __name__ == "__main__":
    # Argument menu / parsing
    parser = argparse.ArgumentParser()
    parser.add_argument("-a", "--artifacts", type=str, default=ARTIFACT_FOLDER,
                        help="Name of the artifacts folder. Default: \"Artifacts\"")
    parser.add_argument("-u", "--lt_url", type=str, required=True,
                        help="URL for LifeTime environment, without the API endpoint. Example: \"https://<lifetime_host>\"")
    parser.add_argument("-t", "--lt_token", type=str, required=True,
                        help="Token for LifeTime API calls.")
    parser.add_argument("-v", "--lt_api_version", type=int, default=LIFETIME_API_VERSION,
                        help="LifeTime API version number. If version <= 10, use 1, if version >= 11, use 2. Default: 2")
    parser.add_argument("-e", "--lt_endpoint", type=str, default=LIFETIME_API_ENDPOINT,
                        help="(optional) Used to set the API endpoint for LifeTime, without the version. Default: \"lifetimeapi/rest\"")
    parser.add_argument("-s", "--source_env", type=str, required=True,
                        help="Name, as displayed in LifeTime, of the source environment where the apps are.")
    parser.add_argument("-d", "--destination_env", type=str, required=True,
                        help="Name, as displayed in LifeTime, of the destination environment where you want to deploy the apps. (if in Airgap mode should be the hostname of the destination environment where you want to deploy the apps)")
    parser.add_argument("-m", "--deploy_msg", type=str, default=DEPLOYMENT_MESSAGE,
                        help="Message you want to show on the deployment plans in LifeTime. Default: \"Automated deploy using OS Pipelines\".")
    parser.add_argument("-l", "--app_list", type=str, required=True,
                        help="Comma separated list of apps you want to deploy. Example: \"App1,App2 With Spaces,App3_With_Underscores\"")
    parser.add_argument("-f", "--manifest_file", type=str,
                        help="(optional) Manifest file path, used if you have a split pipeline for CI and CD, where the CI pipeline will generate the deployment manifest file.")
    parser.add_argument("-o", "--osp_tool_path", type=str, required=True,
                        help="(optional) TODO")
    parser.add_argument("-user", "--airgap_user", type=str, required=True,
                        help="(optional) TODO")
    parser.add_argument("-pass", "--airgap_pass", type=str, required=True,
                        help="(optional) TODO")
    parser.add_argument("-pu", "--cicd_probe_url", type=str, required=True,
                        help="(optional) TODO")
    parser.add_argument("-pv", "--cicd_probe_version", type=str, default=PROBE_API_VERSION,
                        help="(optional) TODO")
    parser.add_argument("-pe", "--cicd_probe_endpoint", type=str, default=PROBE_API_ENDPOINT,
                        help="(optional) TODO")

    args = parser.parse_args()
    
    # Parse the artifact directory
    artifact_dir = args.artifacts
    # Parse the API endpoint
    lt_api_endpoint = args.lt_endpoint
    # Parse the LT Url and split the LT hostname from the HTTP protocol
    # Assumes the default HTTP protocol = https
    lt_http_proto = LIFETIME_HTTP_PROTO
    lt_url = args.lt_url
    if lt_url.startswith("http://"):
        lt_http_proto = "http"
        lt_url = lt_url.replace("http://", "")
    else:
        lt_url = lt_url.replace("https://", "")
    if lt_url.endswith("/"):
        lt_url = lt_url[:-1]
    # Parte LT API Version
    lt_version = args.lt_api_version
    # Parse the LT Token
    lt_token = args.lt_token
    # Parse Source Environment
    source_env = args.source_env
    # Parse Destination Environment
    dest_env = args.destination_env
    # Parse App list
    _apps = args.app_list
    apps = _apps.split(',')
    # Parse Manifest file if it exists
    if args.manifest_file:
        manifest_file = load_data("", args.manifest_file)
    else:
        manifest_file = None
    # Parse Deployment Message
    dep_note = args.deploy_msg
    # Parse Airgap Option

    osp_tool_path = args.osp_tool_path
    credentials = args.airgap_user + " " + args.airgap_pass

    # Parse the CICD Probe API endpoint
    cicd_api_endpoint = args.cicd_probe_endpoint
    # Parse the CICD Probe Url and split the CICD Probe hostname from the HTTP protocol
    # Assumes the default HTTP protocol = "https"
    cicd_http_proto = PROBE_HTTP_PROTO
    cicd_url = args.cicd_probe_url
    if cicd_url.startswith("http://"):
        cicd_http_proto = "http"
        cicd_url = cicd_url.replace("http://", "")
    else:
        cicd_url = cicd_url.replace("https://", "")
    if cicd_url.endswith("/"):
        cicd_url = cicd_url[:-1]
    # Parse CICD Probe API Version
    cicd_version = args.cicd_probe_version

    
    # Calls the main script
    main(artifact_dir, lt_http_proto, lt_url, lt_api_endpoint, lt_version, lt_token, source_env, dest_env, apps, manifest_file, dep_note, osp_tool_path, credentials, cicd_http_proto, cicd_url, cicd_api_endpoint, cicd_version)
