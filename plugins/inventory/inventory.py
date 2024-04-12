#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import (absolute_import, division, print_function)
from ansible.plugins.inventory import BaseInventoryPlugin, Constructable
import boto3
import os

__metaclass__ = type

DOCUMENTATION = '''
    name: ecgalaxy.aws_ssm.inventory
    author:
        - ecgalaxy
    short_description: Ansible SSM dynamic inventory plugin.
    requirements:
        - python3
    extends_documentation_fragment:
        - constructed
    description:
        - Generates a dynamic inventory of online SSM resources, including EC2 instances and AWS Workspaces using hybrid activations.
        - Uses a YAML configuration file aws_ssm.[yml|yaml].
    options:
        plugin:
            description: The name of this plugin.
            type: str
            required: true
            choices:
              - ecgalaxy.aws_ssm.inventory
        region:
            description:
              - The AWS region to use.
              - If empty, the AWS_REGION or AWS_DEFAULT_REGION environment variable is used.
            type: str
            required: false
        bucket_name:
            description:
              - The name of the S3 bucket used for file transfers.
              - If empty, defaults to 'ansible-aws-ssm-{AWS account ID}'.
            type: str
            required: false
        ec2_group_name:
            description:
              - The name of the generated EC2 instances inventory group.
            type: str
            required: false
            default: 'ec2'
        workspace_group_name:
            description:
              - The name of the generated workspaces inventory group.
            type: str
            required: false
            default: 'workspaces'
        managed_instance_profile:
            description:
                - The name of the instance profile to filter EC2 instances managed through SSM.
                - If empty, all EC2 instances are considered.
            type: str
            required: false
        managed_role:
            description:
               - The name of the role to which the AmazonSSMManagedInstanceCore policy is attached for hybrid activations.
               - If empty, hybrid activations are not used.
            type: str
            required: false
        directory_name:
            description:
               - The short name of the AWS Directory used for WorkSpaces.
               - This helps setting end-user related values.
            type: str
            required: false
'''

EXAMPLES = '''
# aws_ssm.yml
plugin: ecgalaxy.aws_ssm.inventory

managed_instance_profile: instance-profile/my-ssm-profile
managed_role: service-role/my-ssm-managed-role

keyed_groups:
  - key: BundleId
    prefix: "bundle"
  - key: DirectoryId
    prefix: "directory"
  - key: WorkspaceProperties.RunningMode
    prefix: "runningmode"

groups:
  prod: "'production' in (Environment)"
  ubuntu: "'Ubuntu' in (PlatformName)"
'''


class InventoryModule(BaseInventoryPlugin, Constructable):
    ''' Host inventory parser for Ansible using a SSM source. '''

    NAME = 'ecgalaxy.aws_ssm.inventory'

    def _populate(self):

        region = self.get_option('region')
        bucket_name = self.get_option('bucket_name')
        ds_name = self.get_option('directory_name')
        aws_region = region if region is not None else os.environ.get('AWS_REGION', os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'))
        aws_account_id = boto3.client('sts', aws_region).get_caller_identity().get('Account')
        aws_ssm_bucket_name = bucket_name if bucket_name is not None else f'ansible-aws-ssm-{aws_account_id}'

        # Get SSM-managed EC2 instances
        managed_instances = self._get_ssm_managed_ec2s(aws_region)

        self.inventory.add_group(self.get_option('ec2_group_name'))

        client = boto3.client('ec2', aws_region)
        profile = self.get_option('managed_instance_profile')
        filters = [{'Name': 'iam-instance-profile.arn', 'Values': [f'arn:aws:iam::{aws_account_id}:{profile}']}] if profile is not None else []
        for instance in managed_instances:
            # TODO: Reduce the number of API calls
            reservations = client.describe_instances(Filters=filters, InstanceIds=[instance['InstanceId']])['Reservations']
            if len(reservations) == 1:
                host = instance['InstanceId']
                end_user = 'ubuntu' if instance['PlatformName'] == 'Ubuntu' else 'admin' if instance['PlatformName'] == 'Debian' else 'ec2-user'

                self.inventory.add_host(host, group=self.get_option('ec2_group_name'))
                self.inventory.set_variable(host, 'ansible_connection', 'aws_ssm')
                self.inventory.set_variable(host, 'ansible_aws_ssm_bucket_name', aws_ssm_bucket_name)
                self.inventory.set_variable(host, 'ansible_end_user', end_user)
                self.inventory.set_variable(host, 'ansible_become_end_user', end_user)
                self.inventory.set_variable(host, 'ansible_aws_ssm_region', aws_region)

                instance = instance | reservations[0]['Instances'][0]
                for tag in instance['Tags']:
                    instance = instance | {tag['Key']: tag['Value']}
                strict = self.get_option('strict')
                self._set_composite_vars(self.get_option('compose'), instance, host, strict=strict)
                self._add_host_to_composed_groups(self.get_option('groups'), instance, host, strict=strict)
                self._add_host_to_keyed_groups(self.get_option('keyed_groups'), instance, host, strict=strict)

        # Get online managed workspaces
        if self.get_option('managed_role') is not None:
            workspaces = self._get_workspaces(aws_region)
            managed_instances = self._get_ssm_managed_instances(aws_region, [self.get_option('managed_role')], ['Online'])
            managed_workspaces = self._get_ssm_managed_workspaces(workspaces, managed_instances)

            self.inventory.add_group(self.get_option('workspace_group_name'))

            client = boto3.client('workspaces', aws_region)
            for key, workspace in managed_workspaces.items():
                host = workspace['UserName'].lower()
                self.inventory.add_host(host, group=self.get_option('workspace_group_name'))
                self.inventory.set_variable(host, 'ansible_host', key)
                self.inventory.set_variable(host, 'ansible_connection', 'aws_ssm')
                self.inventory.set_variable(host, 'ansible_aws_ssm_bucket_name', aws_ssm_bucket_name)
                domain = f'{ds_name}\\' if ds_name is not None else ''
                self.inventory.set_variable(host, 'ansible_end_user', f'{domain}{host}')
                domain = f'@{ds_name}' if ds_name is not None else ''
                self.inventory.set_variable(host, 'ansible_become_end_user', f'{host}{domain}')
                self.inventory.set_variable(host, 'ansible_aws_ssm_region', aws_region)

                # TODO: Decrease the number of API calls
                tags = client.describe_tags(ResourceId=workspace['WorkspaceId'])['TagList']
                for tag in tags:
                    workspace = workspace | {tag['Key']: tag['Value']}

                strict = self.get_option('strict')
                self._set_composite_vars(self.get_option('compose'), workspace, host, strict=strict)
                self._add_host_to_composed_groups(self.get_option('groups'), workspace, host, strict=strict)
                self._add_host_to_keyed_groups(self.get_option('keyed_groups'), workspace, host, strict=strict)

    def verify_file(self, path):
        """Return the possibly of a file being consumable by this plugin."""
        return (
            super(InventoryModule, self).verify_file(path) and
            path.endswith(("aws_ssm.yaml", "aws_ssm.yml")))

    def parse(self, inventory, loader, path, cache=True):
        super(InventoryModule, self).parse(inventory, loader, path, cache)
        self._read_config_data(path)
        self._populate()

    def _get_workspaces(self, region):
        """
        Returns existing workspaces in the provided region.
        """
        client = boto3.client('workspaces', region)
        response = client.describe_workspaces()
        workspaces = response['Workspaces']
        while 'NextToken' in response:
            response = client.describe_workspaces(NextToken=response['NextToken'])
            workspaces.extend(response['Workspaces'])
        return workspaces

    def _get_ssm_managed_instances(self, region, iam_role, ping_status=None, association_status=None):
        """
        Returns instances managed through SSM in the provided region
        and with the provided IAM role.
        """
        client = boto3.client('ssm', region)
        filters = [
            {'Key': 'ResourceType', 'Values': ['ManagedInstance']},
            {'Key': 'IamRole', 'Values': iam_role}
        ]
        if ping_status is not None:
            filters.append({'Key': 'PingStatus', 'Values': ping_status})
        if association_status is not None:
            filters.append({'Key': 'AssociationStatus', 'Values': association_status})
        response = client.describe_instance_information(Filters=filters)
        managed_instances = response['InstanceInformationList']
        while 'NextToken' in response:
            response = client.describe_instance_information(Filters=filters, NextToken=response['NextToken'])
            managed_instances.extend(response['InstanceInformationList'])
        return managed_instances

    def _get_ssm_managed_ec2s(self, region, ping_status=['Online']):
        """
        Returns EC2 instances managed through SSM in the provided region.
        """
        client = boto3.client('ssm', region)
        filters = [
            {'Key': 'ResourceType', 'Values': ['EC2Instance']},
            {'Key': 'AssociationStatus', 'Values': ['Success']},
            {'Key': 'PingStatus', 'Values': ping_status}
        ]
        response = client.describe_instance_information(Filters=filters)
        managed_instances = response['InstanceInformationList']
        while 'NextToken' in response:
            response = client.describe_instance_information(Filters=filters, NextToken=response['NextToken'])
            managed_instances.extend(response['InstanceInformationList'])
        return managed_instances

    def _get_ssm_managed_workspaces(self, workspaces, managed_instances):
        """
        Returns managed workspaces from a list of SSM-managed instances.
        """
        managed_workspaces = {}
        for workspace in workspaces:
            if 'ComputerName' not in workspace:
                break
            computer_name = workspace['ComputerName'].lower()
            found = False
            for managed in managed_instances:
                if 'ComputerName' not in managed:
                    continue
                instance_name = managed['ComputerName'].lower()
                if instance_name.startswith(computer_name):
                    found = True
                    break
            if found:
                managed_workspaces[managed['InstanceId']] = workspace
        return managed_workspaces
