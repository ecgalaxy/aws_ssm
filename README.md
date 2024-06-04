ECGALAXY Ansible aws_ssm collection
===================================

This Ansible collection provides an [inventory plugin](https://docs.ansible.com/ansible/latest/plugins/inventory.html)
for resources managed through
[AWS System Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/what-is-systems-manager.html).

It leverages the [SSM connection plugin](https://docs.ansible.com/ansible/latest/collections/community/aws/aws_ssm_connection.html)
by generating a dynamic inventory of online SSM resources, including EC2 instances and AWS Workspaces using
[hybrid activations](https://docs.aws.amazon.com/systems-manager/latest/userguide/activations.html).

Requirements
------------

- Python 3.x
- boto3

Installation
------------

```
ansible-galaxy collection install ecgalaxy.aws_ssm
```

Example usage
-------------

```
# aws_ssm.yml
---
plugin: ecgalaxy.aws_ssm.inventory

directory_name: myad
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
```

See the [plugin documentation](https://galaxy.ansible.com/ui/repo/published/ecgalaxy/aws_ssm/content/inventory/inventory/)
on Ansible Galaxy.

License
-------

Copyright the European Union 2024.
Licensed under the EUPL-1.2 or later.

Author Information
------------------

ECGALAXY team.
