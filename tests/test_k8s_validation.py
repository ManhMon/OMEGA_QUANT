import re
import yaml
import pathlib
import pytest

WORKSPACE = pathlib.Path(__file__).parent.parent
K8S_ROOT = WORKSPACE / "infra" / "kubernetes" / "mlops"

def parse_memory(mem_str: str) -> float:
    """Convert Kubernetes memory string to gigabytes."""
    match = re.match(r"^(\d+)([MGT]i|[mgt]?)$", mem_str)
    if not match:
        raise ValueError(f"Invalid memory string: {mem_str}")
    val, unit = match.groups()
    val = float(val)
    if unit == "Gi":
        return val
    elif unit == "Mi":
        return val / 1024.0
    elif unit == "Ti":
        return val * 1024.0
    return val / (1024.0 * 1024.0 * 1024.0)

def parse_cpu(cpu_str: str) -> float:
    """Convert Kubernetes CPU string to core count."""
    if cpu_str.endswith("m"):
        return float(cpu_str[:-1]) / 1000.0
    return float(cpu_str)

def test_kustomization_files_exist():
    """Verify all resources declared in kustomization.yaml exist."""
    kust_path = K8S_ROOT / "kustomization.yaml"
    assert kust_path.exists()
    
    with open(kust_path, "r", encoding="utf-8") as f:
        kust = yaml.safe_load(f)
        
    resources = kust.get("resources", [])
    assert len(resources) > 0
    
    for resource in resources:
        res_path = K8S_ROOT / resource
        assert res_path.exists(), f"Resource file not found: {resource}"

def test_k8s_manifests_valid_yaml():
    """Verify all yaml files are syntactically correct and have standard Kubernetes keys."""
    kust_path = K8S_ROOT / "kustomization.yaml"
    with open(kust_path, "r", encoding="utf-8") as f:
        kust = yaml.safe_load(f)
        
    for resource in kust.get("resources", []):
        res_path = K8S_ROOT / resource
        with open(res_path, "r", encoding="utf-8") as f:
            docs = yaml.safe_load_all(f)
            for doc in docs:
                if doc is None:
                    continue
                assert "apiVersion" in doc, f"Missing apiVersion in {resource}"
                assert "kind" in doc, f"Missing kind in {resource}"
                assert "metadata" in doc, f"Missing metadata in {resource}"
                metadata = doc["metadata"]
                assert "name" in metadata, f"Missing metadata.name in {resource}"

def test_resource_quotas_compliance():
    """Verify sum of container resources does not exceed namespace ResourceQuotas."""
    # 1. Parse Quotas
    ns_path = K8S_ROOT / "namespace.yaml"
    quota_doc = None
    with open(ns_path, "r", encoding="utf-8") as f:
        docs = yaml.safe_load_all(f)
        for doc in docs:
            if doc and doc.get("kind") == "ResourceQuota":
                quota_doc = doc
                break
                
    assert quota_doc is not None
    hard = quota_doc["spec"]["hard"]
    quota_req_cpu = parse_cpu(hard["requests.cpu"])
    quota_req_mem = parse_memory(hard["requests.memory"])
    quota_lim_cpu = parse_cpu(hard["limits.cpu"])
    quota_lim_mem = parse_memory(hard["limits.memory"])
    
    # 2. Sum resources in deployments
    total_req_cpu = 0.0
    total_req_mem = 0.0
    total_lim_cpu = 0.0
    total_lim_mem = 0.0
    
    kust_path = K8S_ROOT / "kustomization.yaml"
    with open(kust_path, "r", encoding="utf-8") as f:
        kust = yaml.safe_load(f)
        
    for resource in kust.get("resources", []):
        res_path = K8S_ROOT / resource
        with open(res_path, "r", encoding="utf-8") as f:
            docs = yaml.safe_load_all(f)
            for doc in docs:
                if not doc or doc.get("kind") != "Deployment":
                    continue
                
                pod_spec = doc["spec"]["template"]["spec"]
                # Include init containers if any
                containers = pod_spec.get("containers", []) + pod_spec.get("initContainers", [])
                
                for container in containers:
                    resources = container.get("resources", {})
                    requests = resources.get("requests", {})
                    limits = resources.get("limits", {})
                    
                    if "cpu" in requests:
                        total_req_cpu += parse_cpu(requests["cpu"])
                    if "memory" in requests:
                        total_req_mem += parse_memory(requests["memory"])
                    if "cpu" in limits:
                        total_lim_cpu += parse_cpu(limits["cpu"])
                    if "memory" in limits:
                        total_lim_mem += parse_memory(limits["memory"])
                        
    # 3. Assert sums <= Quota
    assert total_req_cpu <= quota_req_cpu, f"CPU request sum ({total_req_cpu}) exceeds quota ({quota_req_cpu})"
    assert total_req_mem <= quota_req_mem, f"Memory request sum ({total_req_mem}Gi) exceeds quota ({quota_req_mem}Gi)"
    assert total_lim_cpu <= quota_lim_cpu, f"CPU limit sum ({total_lim_cpu}) exceeds quota ({quota_lim_cpu})"
    assert total_lim_mem <= quota_lim_mem, f"Memory limit sum ({total_lim_mem}Gi) exceeds quota ({quota_lim_mem}Gi)"
