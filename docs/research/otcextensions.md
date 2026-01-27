# Research: python-otcextensions Architecture

The **python-otcextensions** project extends OpenStack SDK for Open Telekom Cloud services support.

- Repository: https://github.com/opentelekomcloud/python-otcextensions
- Documentation: https://python-otcextensions.readthedocs.io/

---

## Project Structure

```
python-otcextensions/
├── otcextensions/
│   ├── sdk/                # SDK implementation
│   │   ├── __init__.py     # register_otc_extensions()
│   │   ├── cce/v3/         # CCE service
│   │   │   ├── _proxy.py   # Service proxy
│   │   │   ├── cluster.py  # Resource: Cluster
│   │   │   └── cluster_node.py
│   │   ├── rds/v3/         # RDS service
│   │   ├── vpc/v1/         # VPC service
│   │   └── [30+ services]
│   └── osclient/           # CLI commands
│       ├── cce/
│       │   ├── v2/
│       │   │   └── cluster.py  # ListCluster, CreateCluster commands
│       └── ...
├── setup.cfg               # Entry points
└── requirements.txt
```

---

## Entry Points Mechanism

When the package is installed, otcextensions registers new services via **entry points** in `setup.cfg`:

```ini
[entry_points]
openstack.sdk.connection =
    cce = otcextensions.sdk.cce.v3._proxy:Proxy
    rds = otcextensions.sdk.rds.v3._proxy:Proxy
    dcs = otcextensions.sdk.dcs.v1._proxy:Proxy

openstack.cli.extension =
    cce = otcextensions.osclient.cce.v2
    rds = otcextensions.osclient.rds.v3
```

This allows OpenStack SDK to automatically connect OTC services when creating a `Connection`.

---

## Resource Pattern (Data Model)

Resources inherit from `openstack.resource.Resource` and declaratively describe the API:

```python
from openstack import resource

class Cluster(resource.Resource):
    # JSON keys in API response
    resource_key = 'cluster'      # For single object
    resources_key = 'items'       # For list of objects
    
    # URL template
    base_path = '/clusters'
    
    # Allowed operations
    allow_create = True
    allow_fetch = True
    allow_delete = True
    allow_list = True
    allow_commit = False  # Update
    
    # JSON field to attribute mapping
    name = resource.Body('metadata.name')
    id = resource.Body('metadata.uid')
    status = resource.Body('status.phase')
    cluster_type = resource.Body('spec.type')
    flavor = resource.Body('spec.flavor')
    version = resource.Body('spec.version')
    
    # Nested structures
    host_network = resource.Body('spec.hostNetwork', type=dict)
    container_network = resource.Body('spec.containerNetwork', type=dict)
```

### Key Resource Attributes

| Attribute | Purpose |
|-----------|---------|
| `resource_key` | JSON key for single resource |
| `resources_key` | JSON key for resource list |
| `base_path` | URL template with placeholders |
| `allow_*` | Allowed operation flags |
| `resource.Body()` | JSON field mapping |
| `resource.URI()` | URL parameter mapping |

---

## Proxy Pattern (Operations)

Proxy provides a high-level interface for working with resources:

```python
from openstack import proxy as _proxy
from otcextensions.sdk.cce.v3 import cluster as _cluster

class Proxy(_proxy.Proxy):
    
    def clusters(self, **query):
        """List all clusters."""
        return self._list(_cluster.Cluster, **query)
    
    def get_cluster(self, cluster):
        """Get cluster by ID."""
        return self._get(_cluster.Cluster, cluster)
    
    def find_cluster(self, name_or_id, ignore_missing=True):
        """Find cluster by name or ID."""
        return self._find(_cluster.Cluster, name_or_id,
                         ignore_missing=ignore_missing)
    
    def create_cluster(self, **attrs):
        """Create cluster."""
        return self._create(_cluster.Cluster, **attrs)
    
    def delete_cluster(self, cluster, ignore_missing=True):
        """Delete cluster."""
        return self._delete(_cluster.Cluster, cluster,
                           ignore_missing=ignore_missing)
```

---

## Sub-Resources Pattern

For nested resources (e.g., nodes in cluster), `base_path` with placeholder is used:

```python
class ClusterNode(resource.Resource):
    base_path = '/clusters/%(cluster_id)s/nodes'
    
    # In Proxy:
    def cluster_nodes(self, cluster, **query):
        cluster = self._get_resource(_cluster.Cluster, cluster)
        return self._list(_cluster_node.ClusterNode, 
                         cluster_id=cluster.id, **query)
```

---

## Async Operations and Job Polling

Many OTC services return a **job id** when creating a resource:

```python
# In CLI command with --wait
class CreateCluster(command.ShowOne):
    def take_action(self, parsed_args):
        client = self.app.client_manager.cce
        
        cluster = client.create_cluster(**attrs)
        
        if parsed_args.wait:
            # Wait for creation to complete
            cluster = client.wait_for_status(
                cluster, 
                status='Available',
                failures=['Error'],
                interval=10,
                wait=parsed_args.wait_timeout
            )
        
        return self.columns, cluster
```

This must be considered when generating CLI commands — add `--wait` and `--wait-timeout` options.

---

## OpenStack SDK Integration

Services are registered via `register_otc_extensions()`:

```python
import openstack
from otcextensions import sdk as otc_sdk

# Create connection
conn = openstack.connect(cloud='otc')

# Register OTC extensions
otc_sdk.register_otc_extensions(conn)

# Usage
for cluster in conn.cce.clusters():
    print(f"Cluster: {cluster.name}, Status: {cluster.status}")
```

---

## Service Coverage

Currently ~40 services are covered by OTC Extensions.

**Covered services** (approximate list):
- CCE (Cloud Container Engine)
- RDS (Relational Database Service)
- DCS (Distributed Cache Service)
- DMS (Distributed Message Service)
- Anti-DDoS
- CTS (Cloud Trace Service)
- VPC
- ELB (Elastic Load Balancer)
- and others...

**Not covered:** many new services.

---

## Key Takeaways

- **Declarative model** — Resources describe API via attributes, not code
- **Consistent patterns** — identical structure for 30+ services
- **OpenStack compatibility** — uses OpenStack SDK base classes
- **Entry points** for automatic service registration
- **Job polling** for async operations
- **Incomplete coverage** (13 services) — motivation for auto-generation
- **Target format** — generated SDK must match these patterns
- Automatic setup.cfg updates: The tooling must be able to append new entry points to openstack.sdk.connection and openstack.cli.extension to make the generated service discoverable.
