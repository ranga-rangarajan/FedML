import click
import os

import fedml.api
from prettytable import PrettyTable
from fedml.cli.modules.utils import DefaultCommandGroup
from fedml.api.constants import ApiConstants
from fedml.computing.scheduler.scheduler_entry.constants import Constants
from fedml.computing.scheduler.comm_utils.constants import SchedulerConstants


@click.group("launch", cls=DefaultCommandGroup, default_command='default')
@click.help_option("--help", "-h")
@click.option(
    "--cluster",
    "-c",
    default="",
    type=str,
    help="Please provide a cluster name. If a cluster with that name already exists, it will be used; otherwise, "
         "a new cluster with the provided name will be created."
)
@click.option(
    "--api_key", "-k", type=str, help="user api key.",
)
@click.option(
    "--version",
    "-v",
    type=str,
    default="release",
    help="launch job to which version of MLOps platform. It should be dev, test or release",
)
def fedml_launch(api_key, version, cluster):
    """
    Launch job at the FedML® platform
    """
    pass


@fedml_launch.command(
    "default", help="Launch job at the FedML platform",
    context_settings={"ignore_unknown_options": True}, hidden=True
)
@click.help_option("--help", "-h")
@click.option(
    "--api_key", "-k", type=str, help="user api key.",
)
@click.option(
    "--group",
    "-g",
    type=str,
    default="",
    help="The queue group id on which your job will be scheduled.",
)
@click.option(
    "--version",
    "-v",
    type=str,
    default="release",
    help="launch job to which version of MLOps platform. It should be dev, test or release",
)
@click.option(
    "--cluster",
    "-c",
    default=None,
    type=str,
    help="Please provide a cluster name. If a cluster with that name already exists, it will be used; otherwise, "
         "a new cluster with the provided name will be created."
)
@click.argument("yaml_file", nargs=-1)
def fedml_launch_default(yaml_file, api_key, group, cluster, version):
    """
    Manage resources on the FedML® Launch platform (open.fedml.ai).
    """
    fedml.set_env_version(version)

    if cluster is None:
        _launch_job(yaml_file[0], api_key)
    else:
        _launch_job_with_cluster(yaml_file[0], api_key, cluster)


def _launch_job(yaml_file, api_key):
    _, _, schedule_result = fedml.api.schedule_job(yaml_file, api_key=api_key)

    if _resources_matched_and_confirmed(schedule_result, yaml_file, api_key):
        result = fedml.api.run_scheduled_job(schedule_result=schedule_result, api_key=api_key)
        process_job_result(result)


def _launch_job_with_cluster(yaml_file, api_key, cluster):
    _, _, schedule_result = fedml.api.schedule_job_on_cluster(yaml_file, cluster, api_key)

    if _resources_matched_and_confirmed(schedule_result, yaml_file, api_key):
        cluster_id = getattr(schedule_result, "cluster_id", None)

        if cluster_id is None or cluster_id == "":
            click.echo("Cluster id was not assigned. Please check if the cli arguments are valid")
            return

        cluster_confirmed = fedml.api.confirm_cluster_and_start_job(cluster_id, schedule_result.gpu_matched)

        if cluster_confirmed:
            click.echo("Cluster successfully confirmed and job will be started on cluster soon.")
        else:
            click.echo("Cluster confirmation failed. Please check if the cli arguments are valid")


def _check_match_result(result, yaml_file):
    if result.job_url == "":
        if result.message is not None:
            click.echo(f"Failed to launch the job with response messages: {result.message}")
        else:
            click.echo(f"Failed to launch the job. Please check if the network is available.")

        return ApiConstants.RESOURCE_MATCHED_STATUS_JOB_URL_ERROR

    if result.status == Constants.JOB_START_STATUS_INVALID:
        click.echo(f"\nPlease check your {os.path.basename(yaml_file)} file "
                   f"to make sure the syntax is valid, e.g. "
                   f"whether minimum_num_gpus or maximum_cost_per_hour is valid.")
        return ApiConstants.RESOURCE_MATCHED_STATUS_MATCHED
    elif result.status == Constants.JOB_START_STATUS_BLOCKED:
        click.echo("\nBecause the value of maximum_cost_per_hour is too low,"
                   "we can not find exactly matched machines for your job. \n"
                   "But here we still present machines closest to your expected price as below.")
        return ApiConstants.RESOURCE_MATCHED_STATUS_MATCHED
    elif result.status == Constants.JOB_START_STATUS_QUEUED:
        click.echo("\nNo resource available now, but we can keep your job in the waiting queue.")
        if click.confirm("Do you want to join the queue?", abort=False):
            click.echo("You have confirmed to keep your job in the waiting list.")
            return ApiConstants.RESOURCE_MATCHED_STATUS_QUEUED
        else:
            return ApiConstants.RESOURCE_MATCHED_STATUS_QUEUE_CANCELED
    elif result.status == Constants.JOB_START_STATUS_BIND_CREDIT_CARD_FIRST:
        click.echo("Please bind your credit card before launching the job.")
        return ApiConstants.RESOURCE_MATCHED_STATUS_BIND_CREDIT_CARD_FIRST
    elif result.status == Constants.JOB_START_STATUS_QUERY_CREDIT_CARD_BINDING_STATUS_FAILED:
        click.echo("Failed to query credit card binding status. Please try again later.")
        return ApiConstants.RESOURCE_MATCHED_STATUS_QUERY_CREDIT_CARD_BINDING_STATUS_FAILED

    return ApiConstants.RESOURCE_MATCHED_STATUS_MATCHED


def _match_and_show_resources(result):
    gpu_matched = getattr(result, "gpu_matched", None)
    if gpu_matched is not None and len(gpu_matched) > 0:
        click.echo(f"\nSearched and matched the following GPU resource for your job:")
        gpu_table = PrettyTable(['Provider', 'Instance', 'vCPU(s)', 'Memory(GB)', 'GPU(s)',
                                 'Region', 'Cost', 'Selected'])
        for gpu_device in gpu_matched:
            gpu_table.add_row([gpu_device.gpu_provider, gpu_device.gpu_instance, gpu_device.cpu_count,
                               gpu_device.mem_size,
                               f"{gpu_device.gpu_type}:{gpu_device.gpu_num}",
                               gpu_device.gpu_region, gpu_device.cost, Constants.CHECK_MARK_STRING])
        print(gpu_table)
        click.echo("")

        click.echo(f"You can also view the matched GPU resource with Web UI at: ")
        click.echo(f"{result.job_url}")

        return gpu_matched

    return None


def _resources_matched_and_confirmed(schedule_result, yaml_file, api_key):
    match_result = _check_match_result(schedule_result, yaml_file)
    if match_result == ApiConstants.RESOURCE_MATCHED_STATUS_QUEUE_CANCELED:
        fedml.api.job.stop(schedule_result.job_id, SchedulerConstants.PLATFORM_TYPE_FALCON, api_key=api_key)
        return False
    if match_result == ApiConstants.RESOURCE_MATCHED_STATUS_MATCHED:
        gpu_matched = _match_and_show_resources(schedule_result)
        if gpu_matched is None:
            return False

        if not click.confirm("Do you want to launch the job with the above matched GPU resource?", abort=False):
            click.echo("Cancelling the job with the above matched GPU resource.")
            fedml.api.job.stop(schedule_result.job_id, SchedulerConstants.PLATFORM_TYPE_FALCON, api_key=api_key)
            return False

        click.echo("Launching the job with the above matched GPU resource.")
        return True
    return False


def process_job_result(result):
    if result is None:
        click.echo("Failed to launch the job")
        return

    if result.job_url == "":
        if result.message is not None:
            click.echo(f"Failed to launch the job with response messages: {result.message}")
        else:
            click.echo("Failed to launch the job")

    # List the job status
    job_list_obj = fedml.api.job_list(result.project_name, platform=SchedulerConstants.PLATFORM_TYPE_FALCON,
                                      api_key=api_key, job_id=result.job_id)
    if job_list_obj is not None and len(job_list_obj.job_list) > 0:
        click.echo("")
        click.echo("Your launch result is as follows:")
        job_list_table = PrettyTable(['Job Name', 'Job ID', 'Status', 'Created',
                                      'Spend Time(hour)', 'Cost'])
        jobs_count = 0
        for job in job_list_obj.job_list:
            jobs_count += 1
            job_list_table.add_row([job.job_name, job.job_id, job.status, job.started_time,
                                    job.compute_duration, job.cost])
        click.echo(job_list_table)
    else:
        click.echo("")
